### Lists: filters and sorting

Every list endpoint (`GET /compendium/pois`, `/explorer/tracks`, `/core/rarities`, `/management/event-log`, ...) takes
filters that fit its data and an optional `sort`. Paging works as it always did (`limit`, `offset`; the users list
calls the offset `skip`). The filters of each endpoint are in Swagger.

```bash
curl "http://localhost:8000/api/v1/compendium/pois?q=bahnhof&altitude_min=1000&sort=-altitude_m" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/compendium/pois?near=8.54,47.37&radius_m=5000" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/compendium/pois?compendium_type_id=<id1>&compendium_type_id=<id2>&bbox=7,46,8,47" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/explorer/tracks?distance_min=10000&sport_type_id=<id>&sort=-distance_m" -H "Authorization: Bearer $TOKEN"
```

| Rule | Detail |
|------|--------|
| Paging | Unchanged: `limit` defaults to 1000 (100 on tracks, the event log, jobs and my jobs), `offset` skips rows (`skip` on the users list); tracks, jobs and my jobs allow at most 500 per call, the other lists have no maximum. `limit` or `offset` below 1 / 0 or above 1,000,000,000 answer `422` |
| Counting | `response_pagination.pagination_total` counts the rows that match the filters, not the whole table |
| Sorting | `sort=name` ascending, `sort=-name` descending, one field; the allowed names are in the description of `sort` in Swagger, an unknown name answers `422`. Rows without a value come last; equal values are ordered by `id`, so pages do not repeat or skip rows. Without `sort` each list keeps its old order |
| Text search | `q` searches the name in English, German and Polish (and for some lists the summary, model or e-mail), not case sensitive, at least 2 characters (an empty `q` means no search); `%` and `_` are ordinary characters |
| Values | A filter that names a row (`compendium_type_id`, `sport_type_id`, ...) takes one id or the same parameter several times (`compendium_type_id=a&compendium_type_id=b` means a or b), at most 50. Different filters are combined with AND. A text filter that is sent empty (`kind=`) counts as not given; an id, a number or a date has to be valid or left out. Ranges are `..._min` and `..._max` (both included, whole numbers between -1,000,000,000 and 1,000,000,000); dates are `..._from` (included) and `..._to` (not included), the year between 1900 and 2200; give a time zone (`2026-10-01T00:00:00Z`), without one the time zone of the database session applies |
| Geography | `bbox=min_lon,min_lat,max_lon,max_lat` (west, south, east, north; plain decimals; a box over the 180th meridian has to be asked twice; on regions the area of the region has to touch the box, on POIs the point has to be inside) and, on POIs, `near=lon,lat` with `radius_m` (default 5000, at most 100000) |
| Who sees what | The filters narrow the rows the caller may already see; they never widen them. A viewer who asks for `created_by=<someone>` still only gets what the access policy allows |
| Unknown parameters | A parameter that a list does not know is ignored, as before (so check the spelling of a filter) |
| Errors | An unknown `sort` name, a bad `bbox`, a one-character `q`, more than 50 ids, a number, date, `limit` or `offset` out of range or a NUL character answer `422`; `response_details.error_errors` names the field (`query.sort`, ...) and what is allowed |
