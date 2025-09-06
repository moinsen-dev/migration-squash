"""Migration validation and safety features."""

import sqlite3
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
import hashlib
from dataclasses import dataclass

from .analyzer import MigrationAnalyzer


@dataclass
class SchemaComparison:
    """Results of schema comparison between original and squashed migrations."""
    tables_match: bool
    indexes_match: bool
    constraints_match: bool
    differences: List[str]
    original_schema: Dict[str, Any]
    squashed_schema: Dict[str, Any]


class MigrationValidator:
    """Validates squashed migrations against original migrations."""
    
    def __init__(self):
        self.temp_dbs = []
    
    def validate_squashed_migrations(self, original_dir: Path, squashed_dir: Path, 
                                   db_url: Optional[str] = None) -> bool:
        """Validate that squashed migrations produce the same schema as originals."""
        try:
            # Apply original migrations to temp database
            original_schema = self._apply_migrations_and_extract_schema(original_dir)
            
            # Apply squashed migrations to temp database
            squashed_schema = self._apply_migrations_and_extract_schema(squashed_dir)
            
            # Compare schemas
            comparison = self._compare_schemas(original_schema, squashed_schema)
            
            return comparison.tables_match and comparison.indexes_match
            
        finally:
            self._cleanup_temp_databases()
    
    def _apply_migrations_and_extract_schema(self, migrations_dir: Path) -> Dict[str, Any]:
        """Apply migrations to temporary database and extract schema."""
        # Create temporary database
        temp_db = tempfile.mktemp(suffix='.db')
        self.temp_dbs.append(temp_db)
        
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        
        try:
            # Apply migrations
            self._apply_migrations_to_db(conn, migrations_dir)
            
            # Extract schema
            schema = self._extract_database_schema(conn)
            
            return schema
            
        finally:
            conn.close()
    
    def _apply_migrations_to_db(self, conn: sqlite3.Connection, migrations_dir: Path):
        """Apply all migrations in directory to database."""
        # Get migration files in order
        migration_files = sorted([f for f in migrations_dir.glob("*.sql")])
        
        for migration_file in migration_files:
            try:
                migration_sql = migration_file.read_text(encoding='utf-8')
                
                # Split into individual statements and execute
                statements = self._split_sql_statements(migration_sql)
                
                for statement in statements:
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        conn.execute(statement)
                
                conn.commit()
                
            except sqlite3.Error as e:
                raise RuntimeError(f"Failed to apply migration {migration_file.name}: {e}")
    
    def _split_sql_statements(self, sql: str) -> List[str]:
        """Split SQL into individual statements."""
        # Simple statement splitting on semicolon
        # In a production version, you'd want more sophisticated parsing
        statements = []
        current_statement = ""
        in_string = False
        string_char = None
        
        for char in sql:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            elif char == ';' and not in_string:
                statements.append(current_statement)
                current_statement = ""
                continue
            
            current_statement += char
        
        if current_statement.strip():
            statements.append(current_statement)
        
        return statements
    
    def _extract_database_schema(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Extract complete schema information from database."""
        schema = {
            'tables': {},
            'indexes': {},
            'views': {},
            'triggers': {}
        }
        
        # Get all tables
        cursor = conn.execute("""
            SELECT name, sql FROM sqlite_master 
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        for row in cursor.fetchall():
            table_name = row['name']
            create_sql = row['sql']
            
            # Get table info (columns, types, etc.)
            table_info = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            columns = {col['name']: {
                'type': col['type'],
                'notnull': bool(col['notnull']),
                'default': col['dflt_value'],
                'pk': bool(col['pk'])
            } for col in table_info}
            
            # Get foreign keys
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
            fks = [{'table': fk['table'], 'from': fk['from'], 'to': fk['to']} for fk in foreign_keys]
            
            schema['tables'][table_name] = {
                'create_sql': create_sql,
                'columns': columns,
                'foreign_keys': fks
            }
        
        # Get indexes
        cursor = conn.execute("""
            SELECT name, tbl_name, sql FROM sqlite_master 
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        for row in cursor.fetchall():
            schema['indexes'][row['name']] = {
                'table': row['tbl_name'],
                'sql': row['sql']
            }
        
        return schema
    
    def _compare_schemas(self, original: Dict[str, Any], squashed: Dict[str, Any]) -> SchemaComparison:
        """Compare two database schemas."""
        differences = []
        
        # Compare tables
        tables_match = self._compare_tables(original['tables'], squashed['tables'], differences)
        
        # Compare indexes
        indexes_match = self._compare_indexes(original['indexes'], squashed['indexes'], differences)
        
        return SchemaComparison(
            tables_match=tables_match,
            indexes_match=indexes_match,
            constraints_match=True,  # TODO: Implement constraint comparison
            differences=differences,
            original_schema=original,
            squashed_schema=squashed
        )
    
    def _compare_tables(self, original_tables: Dict, squashed_tables: Dict, 
                       differences: List[str]) -> bool:
        """Compare table schemas."""
        tables_match = True
        
        # Check for missing tables
        original_table_names = set(original_tables.keys())
        squashed_table_names = set(squashed_tables.keys())
        
        missing_in_squashed = original_table_names - squashed_table_names
        extra_in_squashed = squashed_table_names - original_table_names
        
        if missing_in_squashed:
            differences.append(f"Tables missing in squashed: {missing_in_squashed}")
            tables_match = False
        
        if extra_in_squashed:
            differences.append(f"Extra tables in squashed: {extra_in_squashed}")
            tables_match = False
        
        # Compare common tables
        common_tables = original_table_names & squashed_table_names
        
        for table_name in common_tables:
            orig_table = original_tables[table_name]
            squash_table = squashed_tables[table_name]
            
            # Compare columns
            if not self._compare_table_columns(table_name, orig_table['columns'], 
                                             squash_table['columns'], differences):
                tables_match = False
            
            # Compare foreign keys
            if not self._compare_foreign_keys(table_name, orig_table['foreign_keys'],
                                            squash_table['foreign_keys'], differences):
                tables_match = False
        
        return tables_match
    
    def _compare_table_columns(self, table_name: str, original_cols: Dict, 
                              squashed_cols: Dict, differences: List[str]) -> bool:
        """Compare columns of a single table."""
        columns_match = True
        
        orig_col_names = set(original_cols.keys())
        squash_col_names = set(squashed_cols.keys())
        
        if orig_col_names != squash_col_names:
            differences.append(f"Table {table_name}: Column mismatch - "
                             f"original: {orig_col_names}, squashed: {squash_col_names}")
            columns_match = False
        
        # Compare common columns
        common_cols = orig_col_names & squash_col_names
        
        for col_name in common_cols:
            orig_col = original_cols[col_name]
            squash_col = squashed_cols[col_name]
            
            if orig_col != squash_col:
                differences.append(f"Table {table_name}, Column {col_name}: "
                                 f"original: {orig_col}, squashed: {squash_col}")
                columns_match = False
        
        return columns_match
    
    def _compare_foreign_keys(self, table_name: str, original_fks: List, 
                             squashed_fks: List, differences: List[str]) -> bool:
        """Compare foreign keys of a single table."""
        if len(original_fks) != len(squashed_fks):
            differences.append(f"Table {table_name}: Foreign key count mismatch")
            return False
        
        # Sort for comparison
        orig_sorted = sorted(original_fks, key=lambda x: (x['table'], x['from'], x['to']))
        squash_sorted = sorted(squashed_fks, key=lambda x: (x['table'], x['from'], x['to']))
        
        if orig_sorted != squash_sorted:
            differences.append(f"Table {table_name}: Foreign key mismatch")
            return False
        
        return True
    
    def _compare_indexes(self, original_indexes: Dict, squashed_indexes: Dict,
                        differences: List[str]) -> bool:
        """Compare database indexes."""
        # For now, just compare index names and tables
        # In a full implementation, you'd parse the SQL to compare index definitions
        
        orig_index_names = set(original_indexes.keys())
        squash_index_names = set(squashed_indexes.keys())
        
        if orig_index_names != squash_index_names:
            missing = orig_index_names - squash_index_names
            extra = squash_index_names - orig_index_names
            
            if missing:
                differences.append(f"Indexes missing in squashed: {missing}")
            if extra:
                differences.append(f"Extra indexes in squashed: {extra}")
            
            return False
        
        return True
    
    def _cleanup_temp_databases(self):
        """Clean up temporary database files."""
        for temp_db in self.temp_dbs:
            try:
                Path(temp_db).unlink(missing_ok=True)
            except Exception:
                pass  # Ignore cleanup errors
        self.temp_dbs.clear()


class SafetyChecker:
    """Performs safety checks before squashing migrations."""
    
    def check_migrations_safety(self, migrations_dir: Path) -> Dict[str, Any]:
        """Perform comprehensive safety checks on migrations."""
        checks = {
            'has_backup': False,
            'data_loss_risk': False,
            'destructive_operations': [],
            'warnings': [],
            'safe_to_squash': True
        }
        
        analyzer = MigrationAnalyzer()
        analysis = analyzer.analyze_directory(migrations_dir)
        
        # Check for destructive operations
        for migration in analysis.migrations:
            for stmt in migration.statements:
                if stmt.type.value in ['DROP_TABLE', 'DROP_COLUMN']:
                    checks['destructive_operations'].append(f"{migration.name}: {stmt.raw_sql}")
                    checks['data_loss_risk'] = True
                
                if 'DELETE FROM' in stmt.raw_sql.upper():
                    checks['warnings'].append(f"{migration.name}: Contains DELETE statement")
        
        # Check if we have recent backups or backup tables
        for migration in analysis.migrations:
            if any('backup' in stmt.table_name.lower() 
                   for stmt in migration.statements 
                   if stmt.table_name):
                checks['has_backup'] = True
                break
        
        # Overall safety assessment
        if checks['data_loss_risk'] and not checks['has_backup']:
            checks['safe_to_squash'] = False
            checks['warnings'].append("Data loss risk detected without backup patterns")
        
        return checks