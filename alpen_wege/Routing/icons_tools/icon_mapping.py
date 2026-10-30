"""The hand-made part of the icon set: which graphic stands for which key.

Used by build_icon_map.py (a one-off that wrote scripts/icon_sources/icon_map.csv). Keys that equal a Lucide icon name use that icon
without being listed here. Everything else is listed below; a key that is in none of the tables falls back to a coloured badge.
"""

# key -> Lucide icon name (https://lucide.dev, ISC licence). Placeholders that share a glyph with another key are marked in NOTES.
LUCIDE = {
    # achievement categories
    "ach_cat_collection": "library", "ach_cat_consistency": "calendar-check", "ach_cat_distance": "ruler", "ach_cat_elevation": "mountain",
    "ach_cat_endurance": "battery-full", "ach_cat_exploration": "compass", "ach_cat_navigation": "navigation", "ach_cat_nocturnal": "moon",
    "ach_cat_peaks": "mountain-snow", "ach_cat_photography": "camera", "ach_cat_seasonal": "leaf", "ach_cat_social": "users",
    "ach_cat_speed": "gauge", "ach_cat_weather": "cloud-sun",
    # achievement scopes
    "ach_scope_continental": "earth", "ach_scope_daily": "calendar-1", "ach_scope_event": "party-popper", "ach_scope_global": "globe",
    "ach_scope_group": "users", "ach_scope_lifetime": "infinity", "ach_scope_local": "map-pin", "ach_scope_monthly": "calendar-range",
    "ach_scope_national": "flag", "ach_scope_personal": "user", "ach_scope_regional": "map", "ach_scope_weekly": "calendar-days",
    "ach_scope_yearly": "calendar-sync",
    # achievement types
    "ach_type_challenge": "swords", "ach_type_collaborative": "handshake", "ach_type_cumulative": "sigma", "ach_type_hidden": "eye-off",
    "ach_type_milestone": "milestone", "ach_type_progressive": "trending-up", "ach_type_repeatable": "repeat", "ach_type_seasonal": "snowflake",
    "ach_type_single": "circle-dot", "ach_type_streak": "flame", "ach_type_tiered": "layers", "ach_type_time_limited": "hourglass",
    # resource types
    "article": "newspaper", "emoji_events": "trophy", "flight": "plane", "gps_fixed": "locate-fixed", "photo_camera": "camera",
    "place": "map-pin", "style": "gallery-vertical-end", "terrain": "mountain",
    # compendium types that are not a Lucide name (some look like Font Awesome names)
    "barn": "warehouse", "bat": "bird", "bridge-suspension": "bridge", "building-library": "landmark", "carabiner": "link",
    "cave": "pickaxe", "chair": "cable-car", "cheese": "milk", "city": "building-2", "cube": "box", "deer": "paw-print", "fire": "flame",
    "fountain": "droplets", "glass": "martini", "golf": "flag-triangle-right", "grass": "wheat", "gun": "crosshair", "horse": "paw-print",
    "house-chimney": "house", "house-chimney-user": "house-plus", "house-flag": "flag", "lake": "waves", "land-layers": "layers",
    "masks-theater": "drama", "monument": "landmark", "mountain-pass": "mountain", "none": "train-front", "person-jumping": "zap",
    "picnic": "sandwich", "plant": "sprout", "rope": "cable", "ski": "snowflake", "ski-nordic": "snowflake", "star-badge": "badge-check",
    "swim": "waves", "thermometer-hot": "thermometer-sun", "tower": "radio-tower", "tram": "tram-front", "tree": "trees",
    "umbrella-beach": "umbrella", "water": "droplets", "wind-turbine": "fan",
    # the generic ones used by many rows
    "company": "building-2", "gear_type": "backpack",
    # points
    "point_achievement": "award", "point_activity": "activity", "point_card": "id-card", "point_challenge": "swords", "point_comment": "message-circle",
    "point_community": "users-round", "point_daily_bonus": "gift", "point_distance_milestone": "ruler", "point_elevation_milestone": "mountain",
    "point_first_ascent": "flag-triangle-right", "point_level_up": "chevrons-up", "point_photo": "camera", "point_poi": "map-pin",
    "point_rating": "star", "point_referral": "user-plus", "point_region_completed": "map-pinned", "point_route_created": "route",
    "point_streak": "flame", "point_summit": "mountain-snow", "point_weekly_goal": "target",
    # posts
    "post_announcement": "megaphone", "post_condition": "info", "post_event": "calendar", "post_gear_review": "backpack", "post_live": "radio",
    "post_lost_found": "search", "post_meetup": "users", "post_photo": "image", "post_poll": "chart-bar", "post_question": "circle-help",
    "post_route_share": "share-2", "post_tip": "lightbulb", "post_trip_report": "notebook-pen", "post_video": "video", "post_warning": "triangle-alert",
    # region types
    "region_type_canton": "landmark", "region_type_district": "map", "region_type_municipality": "building-2",
    # schedule status
    "schedule_aborted": "octagon-x", "schedule_cancelled": "ban", "schedule_completed": "circle-check", "schedule_confirmed": "calendar-check",
    "schedule_draft": "file-pen", "schedule_failed": "circle-x", "schedule_in_progress": "loader", "schedule_on_hold": "circle-pause",
    "schedule_planned": "calendar-clock", "schedule_postponed": "clock-arrow-down",
    # snow
    "snow_corn": "wheat", "snow_crusty": "layers", "snow_firn": "mountain-snow", "snow_fresh": "snowflake", "snow_icy": "thermometer-snowflake",
    "snow_none": "ban", "snow_packed": "layers", "snow_packed_powder": "layers", "snow_powder": "snowflake", "snow_sastrugi": "waves",
    "snow_slushy": "cloud-drizzle", "snow_wet": "droplet", "snow_wind_blown": "wind",
    # sports
    "sport_alpine": "mountain-snow", "sport_backcountry_ski": "snowflake", "sport_bouldering": "box", "sport_canyoning": "waves",
    "sport_cycling": "bike", "sport_downhill": "bike", "sport_enduro": "bike", "sport_fastpacking": "backpack", "sport_gravel": "bike",
    "sport_hiking": "footprints", "sport_ice_climbing": "snowflake", "sport_mtb": "bike", "sport_road_cycling": "bike", "sport_rock_climbing": "mountain",
    "sport_scrambling": "mountain", "sport_ski_mountaineering": "mountain-snow", "sport_ski_touring": "snowflake", "sport_snowshoeing": "footprints",
    "sport_splitboard": "snowflake", "sport_trail_running": "timer", "sport_via_ferrata": "cable", "sport_winter_hiking": "footprints",
    "sport_xc_ski": "snowflake",
    # trail conditions
    "trail_boggy": "droplets", "trail_closed": "ban", "trail_dry": "sun", "trail_fallen_trees": "tree-pine", "trail_flooded": "waves", "trail_icy": "snowflake",
    "trail_loose_gravel": "grip", "trail_muddy": "droplets", "trail_overgrown": "sprout", "trail_rocky": "mountain", "trail_rooty": "tree-deciduous",
    "trail_snow": "snowflake", "trail_washed_out": "cloud-rain", "trail_well_maintained": "badge-check", "trail_wet": "droplet",
    # waypoints
    "waypoint_border": "flag", "waypoint_bridge": "bridge", "waypoint_bus_stop": "bus", "waypoint_cable_car": "cable-car", "waypoint_campsite": "tent",
    "waypoint_cave": "pickaxe", "waypoint_chapel": "church", "waypoint_danger": "triangle-alert", "waypoint_first_aid": "briefcase-medical",
    "waypoint_ford": "waves", "waypoint_gate": "fence", "waypoint_hut": "house", "waypoint_junction": "split", "waypoint_ladder": "arrow-up-from-line",
    "waypoint_lake": "waves", "waypoint_parking": "square-parking", "waypoint_pass": "mountain", "waypoint_photo_spot": "camera",
    "waypoint_rest_area": "armchair", "waypoint_restaurant": "utensils", "waypoint_ruins": "landmark", "waypoint_shelter": "tent-tree",
    "waypoint_spring": "droplet", "waypoint_summit": "mountain-snow", "waypoint_toilet": "toilet", "waypoint_trailhead": "signpost",
    "waypoint_train_station": "train-front", "waypoint_viewpoint": "binoculars", "waypoint_water": "droplet", "waypoint_waterfall": "waves",
    # weather
    "weather_clear_night": "moon", "weather_cloudy": "cloud", "weather_drizzle": "cloud-drizzle", "weather_foggy": "cloud-fog", "weather_hail": "cloud-hail",
    "weather_hazy": "haze", "weather_misty": "cloud-fog", "weather_overcast": "cloudy", "weather_partly_cloudy": "cloud-sun", "weather_rainy": "cloud-rain",
    "weather_sleet": "cloud-snow", "weather_snowy": "snowflake", "weather_stormy": "cloud-lightning", "weather_sunny": "sun",
    "weather_thunderstorm": "cloud-lightning", "weather_windy": "wind",
}

# a small tag in the corner of the glyph, for sports that would otherwise look the same (the glyph is the same, the tag tells them apart)
TAGS = {
    "sport_road_cycling": "RD", "sport_gravel": "GR", "sport_mtb": "MT", "sport_enduro": "EN", "sport_downhill": "DH",
    "sport_backcountry_ski": "BC", "sport_ice_climbing": "IC", "sport_ski_touring": "ST", "sport_splitboard": "SB", "sport_xc_ski": "XC",
    "sport_ski_mountaineering": "SM", "sport_scrambling": "SC", "sport_snowshoeing": "SS", "sport_winter_hiking": "WH",
}

# generated bars: key -> (filled bars, total bars, ramp 'up' = more bars is harder (green to red) or 'down' = more bars is better (red to green))
BARS = {
    "difficulty_very_easy": (1, 7, "up"), "difficulty_easy": (2, 7, "up"), "difficulty_moderate": (3, 7, "up"), "difficulty_difficult": (4, 7, "up"),
    "difficulty_very_difficult": (5, 7, "up"), "difficulty_expert": (6, 7, "up"), "difficulty_extreme": (7, 7, "up"),
    "visibility_excellent": (8, 8, "down"), "visibility_very_good": (7, 8, "down"), "visibility_good": (6, 8, "down"), "visibility_moderate": (5, 8, "down"),
    "visibility_poor": (4, 8, "down"), "visibility_low": (3, 8, "down"), "visibility_very_low": (2, 8, "down"), "visibility_whiteout": (1, 8, "down"),
}

# keys drawn as the Lucide gem in the colour of the value (the colour comes from push_data/core_ref_rarity.csv)
GEM = {"rarity_common", "rarity_uncommon", "rarity_rare", "rarity_epic", "rarity_legendary", "rarity_mythic"}

# a glyph that several keys share: explained in the Excel so you know which ones to redraw first
PLACEHOLDER_NOTE = "same glyph as other keys: replace with a real drawing when you have one"
