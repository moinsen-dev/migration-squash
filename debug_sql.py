#!/usr/bin/env python3

import sqlite3
import sys

# Read the squashed SQL file
with open('/Users/udi/work/moinsen/ideas/mcp-hive/tools/migration-squash/test_output/001_squashed_schema.sql', 'r') as f:
    sql_content = f.read()

# Create a test database
conn = sqlite3.connect(':memory:')

# Look for CREATE TABLE statements using regex
import re

create_table_pattern = r'CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);'

matches = re.findall(create_table_pattern, sql_content, re.IGNORECASE | re.DOTALL)
print(f"Found {len(matches)} CREATE TABLE statements using regex")

# Try a different approach - split on CREATE TABLE
statements = re.split(r'(CREATE\s+(?:VIRTUAL\s+)?TABLE[^;]+;)', sql_content, flags=re.IGNORECASE | re.DOTALL)

create_table_count = 0
for i, statement in enumerate(statements):
    statement = statement.strip()
    if statement and 'CREATE TABLE' in statement.upper():
        create_table_count += 1
        try:
            conn.execute(statement)
            table_name = re.search(r'CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', statement, re.IGNORECASE)
            if table_name:
                print(f"✅ CREATE TABLE {create_table_count}: {table_name.group(1)}")
            else:
                print(f"✅ CREATE TABLE {create_table_count}: OK")
        except sqlite3.Error as e:
            print(f"❌ CREATE TABLE {create_table_count}: {e}")
            table_name = re.search(r'CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', statement, re.IGNORECASE)
            if table_name:
                print(f"Table: {table_name.group(1)}")
            print("Statement preview:")
            print(statement[:500] + "..." if len(statement) > 500 else statement)
            print("---")
            break

print(f"Total CREATE TABLE statements processed: {create_table_count}")

conn.close()