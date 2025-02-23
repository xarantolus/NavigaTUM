from utils import TranslatableStr as _


def extract_calendar_urls(data):
    """Extracts the calendar from the tumonline data sets it to the proper value."""
    for entry in data.values():
        if entry.get("tumonline_data", {}).get("calendar", None):
            url = f"https://campus.tum.de/tumonline/{entry['tumonline_data']['calendar']}"
            entry["props"]["calendar_url"] = url


def compute_props(data):
    """
    Create the "computed" value in "props".
    """
    for _id, entry in data.items():
        if "props" in entry:
            props = entry["props"]
            computed = _gen_computed_props(_id, entry, props)

            # Reformat if required (just to have less verbosity in the code above)
            for i, computed_prop in enumerate(computed):
                if "name" not in computed_prop:
                    computed[i] = {"name": list(computed_prop.keys())[0], "text": list(computed_prop.values())[0]}

            entry["props"]["computed"] = computed


def _append_if_present(props, computed_results, key, human_name):
    if key in props:
        computed_results.append({human_name: str(props[key])})


def _gen_computed_props(_id, entry, props):
    computed = []
    if "ids" in props:
        _append_if_present(props["ids"], computed, "b_id", _("Gebäudekennung"))
        _append_if_present(props["ids"], computed, "roomcode", _("Raumkennung"))
        if "arch_name" in props["ids"]:
            computed.append({_("Architekten-Name"): props["ids"]["arch_name"].split("@")[0]})
    if "b_prefix" in entry and entry["b_prefix"] != _id:
        b_prefix = [entry["b_prefix"]] if isinstance(entry["b_prefix"], str) else entry["b_prefix"]
        building_names = ", ".join([p.ljust(4, "x") for p in b_prefix])
        computed.append({_("Gebäudekennungen"): building_names})
    if "address" in props:
        address = props["address"]
        computed.append({_("Adresse"): f"{address['street']}, {address['plz_place']}"})
    if "stats" in props:
        _append_if_present(props["stats"], computed, "n_buildings", _("Anzahl Gebäude"))
        _append_if_present(props["stats"], computed, "n_seats", _("Sitzplätze"))
        if "n_rooms" in props["stats"]:
            if props["stats"]["n_rooms"] == props["stats"]["n_rooms_reg"]:
                computed.append({_("Anzahl Räume"): str(props["stats"]["n_rooms"])})
            else:
                value = _("{n_rooms} ({n_rooms_reg} ohne Flure etc.)").format(
                    n_rooms=props["stats"]["n_rooms"],
                    n_rooms_reg=props["stats"]["n_rooms_reg"],
                )
                computed.append({_("Anzahl Räume"): value})
    if "generic" in props:
        for entity in props["generic"]:
            if isinstance(entity[1], dict):
                computed.append({"name": entity[0], **entity[1]})
            else:
                computed.append({"name": entity[0], "text": entity[1]})
    return computed


def localize_links(data):
    """
    Reformat the "links" value in "props" to be explicitly localized.
    This is a convenience function for the source data format that converts e.g.:
      `text: "<str>"`
    into
      `text: { de: "<str>", en: "<str>" }`
    """
    for _id, entry in data.items():
        links = entry.get("props", {}).get("links", None)
        if links:
            for link in links:
                if isinstance(link["text"], str):
                    link["text"] = {"de": link["text"], "en": link["text"]}
                if isinstance(link["url"], str):
                    link["url"] = {"de": link["url"], "en": link["url"]}


def generate_buildings_overview(data):
    """
    Generate the "buildings_overview" section
    """
    for _id, entry in data.items():
        if entry["type"] not in {"area", "site", "campus"} or "children_flat" not in entry:
            continue

        options = entry.get("generators", {}).get("buildings_overview", {"n_visible": 6, "list_start": []})

        # Collect buildings to display for this entry.
        buildings = []
        for child_id in entry["children"]:
            child = data[child_id]
            if child["type"] in {"area", "site", "campus", "building", "joined_building"}:
                buildings.append(child)
        # for child_id in entry["children_flat"]:
        #    child = data[child_id]
        #    if child["type"] == "joined_building" or \
        #       (child["type"] == "building"
        #        and data[child["parents"][-1]]["type"] != "joined_building"):
        #        buildings.append(child)
        # Entries are sorted alphabetically in second order to be predictable
        buildings = sorted(buildings, key=lambda e: (len(e.get("children_flat", [])), e["name"]), reverse=True)

        # The "list_start" can overwrite how the list of buildings starts,
        # and optionally also add other entries. All other entries are appended
        # after them.
        merged_ids = options["list_start"] + [b["id"] for b in buildings if b["id"] not in options["list_start"]]

        b_overview = entry.setdefault("sections", {}).setdefault("buildings_overview", {})
        b_overview["n_visible"] = options["n_visible"]
        b_overview["entries"] = []
        for child_id in merged_ids:
            try:
                child = data[child_id]
            except KeyError as err:
                raise RuntimeError(f"Unknown id '{child_id}' when generating buildings_overview for '{_id}'") from err

            n_rooms = child["props"]["stats"].get("n_rooms", 0)
            n_buildings = child["props"]["stats"].get("n_buildings", 0)
            if child["type"] in {"building", "joined_building"}:
                if n_rooms == 0:
                    subtext = _("Keine Räume bekannt")
                else:
                    subtext = _("{n_rooms} Räume").format(n_rooms=n_rooms)
            elif child["type"] == "area":
                subtext = _("{n_buildings} Gebäude, {n_rooms} Räume").format(n_buildings=n_buildings, n_rooms=n_rooms)
            elif child["type"] == "site":
                subtext = _("{n_buildings} Gebäude, {n_rooms} Räume (Außenstelle)").format(
                    n_buildings=n_buildings,
                    n_rooms=n_rooms,
                )
            else:
                raise RuntimeError(
                    f"Cannot generate buildings_overview subtext for type '{child['type']}', "
                    f"for: '{_id}', child id: '{child_id}'",
                )

            b_overview["entries"].append(
                {
                    "id": child_id,
                    "name": child["short_name"] if "short_name" in child else child["name"],
                    "subtext": subtext,
                    "thumb": child["img"][0]["name"] if child.get("img", []) else None,
                },
            )


def generate_rooms_overview(data):
    """
    Generate the "rooms_overview" section
    """
    for _id, entry in data.items():
        # if entry["type"] not in {"building", "joined_building", "virtual_room"} or \
        if (
            entry["type"] not in {"area", "site", "campus", "building", "joined_building", "virtual_room"}
            or "children_flat" not in entry
        ):
            continue

        rooms = {}
        for child_id in entry["children_flat"]:
            child = data[child_id]
            if child["type"] == "room":
                usage = child["usage"] if "usage" in child else {"name": _("Unbekannt")}
                rooms.setdefault(usage["name"], []).append(
                    {
                        "id": child_id,
                        "name": child["name"],
                    },
                )

        r_overview = entry.setdefault("sections", {}).setdefault("rooms_overview", {})
        r_overview["usages"] = [
            {
                "name": u[0],
                "count": len(u[1]),
                "children": sorted(u[1], key=lambda r: r["name"]),
            }
            for u in sorted(rooms.items(), key=lambda e: e[0])
        ]
