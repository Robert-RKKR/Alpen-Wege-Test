#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PUSH_DIR="$SCRIPT_DIR/push_data"
ORDER_FILE="$PUSH_DIR/order.json"
CONTAINER="alpenwege-postgres"
DB_USER="alpenwege"
DB_NAME="alpenwege"

if [ ! -f "$ORDER_FILE" ]; then
    echo "ERROR: $ORDER_FILE not found"
    exit 1
fi

TABLES=$(python3 -c "import json,sys; [print(t) for t in json.load(open(sys.argv[1]))['tables']]" "$ORDER_FILE")

if [ "${1:-}" = "--clean" ]; then
    echo "=== Truncating tables in reverse order ==="
    REVERSED=$(echo "$TABLES" | tac)
    for table in $REVERSED; do
        echo "  TRUNCATE $table"
        sudo docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
            "TRUNCATE TABLE $table CASCADE;" 2>/dev/null || true
    done
    echo ""
fi

echo "=== Importing CSVs ==="
loaded=0
skipped=0

for table in $TABLES; do
    csv="$PUSH_DIR/${table}.csv"
    if [ -f "$csv" ]; then
        echo "  LOAD $table <- $(basename "$csv")"
        table_columns=$(sudo docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
            "SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_name = '$table';")
        tmpfile=$(mktemp)
        python3 "$SCRIPT_DIR/csv_to_pg_arrays.py" "$table_columns" < "$csv" > "$tmpfile"
        columns=$(head -1 "$tmpfile")
        sudo docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
            "CREATE TEMP TABLE tmp_import (LIKE $table INCLUDING DEFAULTS);
             COPY tmp_import ($columns) FROM STDIN WITH (FORMAT csv, HEADER true);
             INSERT INTO $table SELECT * FROM tmp_import ON CONFLICT DO NOTHING;
             DROP TABLE tmp_import;" < "$tmpfile"
        rm -f "$tmpfile"
        loaded=$((loaded + 1))
    else
        skipped=$((skipped + 1))
    fi
done

echo ""
echo "Done: $loaded loaded, $skipped skipped (no CSV found)"