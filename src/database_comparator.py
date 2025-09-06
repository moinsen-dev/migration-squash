"""Advanced database schema comparison for migration validation."""

import sqlite3
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


@dataclass
class SchemaElement:
    """Represents a database schema element."""
    name: str
    type: str  # 'table', 'index', 'trigger', 'view'
    sql: Optional[str]
    table: Optional[str] = None  # For indexes/triggers
    columns: Optional[Dict[str, Any]] = None  # For tables


@dataclass 
class ComparisonResult:
    """Results of database schema comparison."""
    identical: bool
    differences: List[str]
    original_schema: Dict[str, Any]
    squashed_schema: Dict[str, Any]
    missing_in_squashed: List[str]
    extra_in_squashed: List[str]
    modified_elements: List[str]


class DatabaseComparator:
    """Advanced database schema comparison for migration validation."""
    
    def __init__(self):
        self.temp_dbs = []
    
    def compare_migrations(self, original_dir: Path, squashed_dir: Path, output_dir: Path = None) -> ComparisonResult:
        """Compare schemas produced by original vs squashed migrations."""
        console.print("🔍 [blue]Creating test databases for comparison...[/blue]")
        
        # Use squashed directory as output location if not specified
        if output_dir is None:
            output_dir = squashed_dir
        
        try:
            # Create databases from migrations in the output directory
            original_db = self._create_database_from_migrations(original_dir, "original", output_dir)
            squashed_db = self._create_database_from_migrations(squashed_dir, "squashed", output_dir)
            
            # Extract complete schemas
            console.print("📋 [blue]Extracting database schemas...[/blue]")
            original_schema = self._extract_complete_schema(original_db)
            squashed_schema = self._extract_complete_schema(squashed_db)
            
            # Perform detailed comparison
            console.print("🔍 [blue]Performing detailed schema comparison...[/blue]")
            result = self._compare_schemas_detailed(original_schema, squashed_schema)
            
            # Keep databases for user inspection - don't clean up
            console.print(f"💾 [green]Comparison databases saved:[/green]")
            console.print(f"  📁 Original database: [cyan]{Path(original_db).name}[/cyan]")
            console.print(f"  📁 Squashed database: [cyan]{Path(squashed_db).name}[/cyan]")
            
            return result
            
        except Exception as e:
            # Only cleanup on error
            self._cleanup_temp_databases()
            raise
    
    def _create_database_from_migrations(self, migrations_dir: Path, label: str, output_dir: Path) -> str:
        """Create a database by applying all migrations in directory."""
        # Create database with clear name in the output directory
        db_path = output_dir / f"{label}.db"
        
        # Remove existing database if it exists
        if db_path.exists():
            db_path.unlink()
            
        self.temp_dbs.append(str(db_path))
        
        console.print(f"  📁 Creating {label} database: [cyan]{db_path.name}[/cyan]")
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        try:
            # Get migration files in order
            migration_files = sorted([f for f in migrations_dir.glob("*.sql")])
            
            for migration_file in migration_files:
                console.print(f"    📄 Applying {migration_file.name}")
                
                migration_sql = migration_file.read_text(encoding='utf-8')
                
                # Split and execute statements
                statements = self._split_sql_statements(migration_sql)
                for statement in statements:
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        try:
                            conn.execute(statement)
                        except sqlite3.Error as e:
                            console.print(f"    ⚠️  [yellow]Warning in {migration_file.name}: {e}[/yellow]")
                            # Continue with other statements
                
                conn.commit()
                
        except Exception as e:
            console.print(f"❌ [red]Error creating {label} database: {e}[/red]")
            raise
        finally:
            conn.close()
        
        return str(db_path)
    
    def _extract_complete_schema(self, db_path: str) -> Dict[str, Any]:
        """Extract complete schema information from database."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        schema = {
            'tables': {},
            'indexes': {},
            'triggers': {},
            'views': {},
            'virtual_tables': {}
        }
        
        try:
            # Get all schema objects
            cursor = conn.execute("""
                SELECT type, name, tbl_name, sql 
                FROM sqlite_master 
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
            """)
            
            for row in cursor.fetchall():
                obj_type = row['type']
                obj_name = row['name'] 
                table_name = row['tbl_name']
                sql = row['sql']
                
                if obj_type == 'table':
                    # Regular table
                    if sql and 'VIRTUAL TABLE' not in sql.upper():
                        schema['tables'][obj_name] = self._extract_table_schema(conn, obj_name, sql)
                    # Virtual table  
                    else:
                        schema['virtual_tables'][obj_name] = {
                            'sql': sql,
                            'table': table_name
                        }
                elif obj_type == 'index':
                    schema['indexes'][obj_name] = {
                        'sql': sql,
                        'table': table_name
                    }
                elif obj_type == 'trigger':
                    schema['triggers'][obj_name] = {
                        'sql': sql,
                        'table': table_name
                    }
                elif obj_type == 'view':
                    schema['views'][obj_name] = {
                        'sql': sql
                    }
            
        finally:
            conn.close()
        
        return schema
    
    def _extract_table_schema(self, conn: sqlite3.Connection, table_name: str, create_sql: str) -> Dict[str, Any]:
        """Extract detailed table schema including columns and constraints."""
        # Get column information
        columns = {}
        column_info = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        
        for col in column_info:
            columns[col['name']] = {
                'type': col['type'],
                'notnull': bool(col['notnull']),
                'default': col['dflt_value'],
                'pk': bool(col['pk']),
                'position': col['cid']
            }
        
        # Get foreign keys
        foreign_keys = []
        fk_info = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        
        for fk in fk_info:
            foreign_keys.append({
                'column': fk['from'],
                'references_table': fk['table'], 
                'references_column': fk['to'],
                'on_delete': fk['on_delete'],
                'on_update': fk['on_update']
            })
        
        return {
            'create_sql': create_sql,
            'columns': columns,
            'foreign_keys': foreign_keys
        }
    
    def _compare_schemas_detailed(self, original: Dict[str, Any], squashed: Dict[str, Any]) -> ComparisonResult:
        """Perform detailed comparison of two database schemas."""
        differences = []
        missing_in_squashed = []
        extra_in_squashed = []
        modified_elements = []
        
        # Compare each schema category
        for category in ['tables', 'indexes', 'triggers', 'views', 'virtual_tables']:
            orig_items = set(original[category].keys())
            squash_items = set(squashed[category].keys())
            
            # Find missing and extra items
            missing = orig_items - squash_items
            extra = squash_items - orig_items
            
            for item in missing:
                missing_in_squashed.append(f"{category[:-1]}: {item}")
                differences.append(f"Missing {category[:-1]} in squashed: {item}")
            
            for item in extra:
                extra_in_squashed.append(f"{category[:-1]}: {item}")
                differences.append(f"Extra {category[:-1]} in squashed: {item}")
            
            # Compare common items
            common = orig_items & squash_items
            for item in common:
                if category == 'tables':
                    # Detailed table comparison
                    table_diffs = self._compare_table_schemas(item, original[category][item], squashed[category][item])
                    if table_diffs:
                        differences.extend(table_diffs)
                        modified_elements.append(f"table: {item}")
                else:
                    # Compare SQL for other objects
                    orig_sql = original[category][item].get('sql', '').strip()
                    squash_sql = squashed[category][item].get('sql', '').strip()
                    
                    if orig_sql != squash_sql:
                        differences.append(f"{category[:-1].title()} {item}: SQL differs")
                        modified_elements.append(f"{category[:-1]}: {item}")
        
        return ComparisonResult(
            identical=len(differences) == 0,
            differences=differences,
            original_schema=original,
            squashed_schema=squashed,
            missing_in_squashed=missing_in_squashed,
            extra_in_squashed=extra_in_squashed,
            modified_elements=modified_elements
        )
    
    def _compare_table_schemas(self, table_name: str, original: Dict[str, Any], squashed: Dict[str, Any]) -> List[str]:
        """Compare two table schemas in detail."""
        differences = []
        
        # Compare columns
        orig_cols = original['columns']
        squash_cols = squashed['columns']
        
        orig_col_names = set(orig_cols.keys())
        squash_col_names = set(squash_cols.keys())
        
        # Missing columns
        missing_cols = orig_col_names - squash_col_names
        for col in missing_cols:
            differences.append(f"Table {table_name}: Missing column '{col}'")
        
        # Extra columns  
        extra_cols = squash_col_names - orig_col_names
        for col in extra_cols:
            differences.append(f"Table {table_name}: Extra column '{col}'")
        
        # Compare common columns
        common_cols = orig_col_names & squash_col_names
        for col in common_cols:
            orig_col = orig_cols[col]
            squash_col = squash_cols[col]
            
            for attr in ['type', 'notnull', 'default', 'pk']:
                if orig_col[attr] != squash_col[attr]:
                    differences.append(f"Table {table_name}, Column {col}: {attr} differs - original: {orig_col[attr]}, squashed: {squash_col[attr]}")
        
        # Compare foreign keys
        orig_fks = set((fk['column'], fk['references_table'], fk['references_column']) for fk in original['foreign_keys'])
        squash_fks = set((fk['column'], fk['references_table'], fk['references_column']) for fk in squashed['foreign_keys'])
        
        missing_fks = orig_fks - squash_fks
        extra_fks = squash_fks - orig_fks
        
        for fk in missing_fks:
            differences.append(f"Table {table_name}: Missing foreign key {fk[0]} -> {fk[1]}({fk[2]})")
        
        for fk in extra_fks:
            differences.append(f"Table {table_name}: Extra foreign key {fk[0]} -> {fk[1]}({fk[2]})")
        
        return differences
    
    def display_comparison_results(self, result: ComparisonResult) -> None:
        """Display comparison results in a formatted way."""
        if result.identical:
            console.print(Panel("✅ [green]SCHEMAS IDENTICAL[/green]\nThe squashed migration produces an identical schema to the original migrations.", 
                              title="🎉 Validation Passed", border_style="green"))
            return
        
        # Show summary
        summary_text = f"❌ [red]SCHEMAS DIFFER[/red]\n"
        summary_text += f"Total differences: {len(result.differences)}\n"
        summary_text += f"Missing elements: {len(result.missing_in_squashed)}\n"
        summary_text += f"Extra elements: {len(result.extra_in_squashed)}\n"
        summary_text += f"Modified elements: {len(result.modified_elements)}"
        
        console.print(Panel(summary_text, title="❌ Validation Failed", border_style="red"))
        
        # Show detailed differences
        if result.differences:
            console.print("\n📋 [bold]Detailed Differences:[/bold]")
            
            table = Table(title="Schema Differences")
            table.add_column("Type", style="cyan")
            table.add_column("Issue", style="yellow")
            
            for diff in result.differences[:20]:  # Limit to first 20 for readability
                if ": " in diff:
                    issue_type, description = diff.split(": ", 1)
                    table.add_row(issue_type, description)
                else:
                    table.add_row("General", diff)
            
            console.print(table)
            
            if len(result.differences) > 20:
                console.print(f"\n... and {len(result.differences) - 20} more differences")
    
    def _split_sql_statements(self, sql: str) -> List[str]:
        """Split SQL into individual statements, handling triggers and complex statements."""
        statements = []
        current_statement = ""
        in_string = False
        string_char = None
        paren_depth = 0
        in_trigger = False
        
        lines = sql.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            
            # Check for trigger start
            if line.upper().startswith('CREATE TRIGGER'):
                in_trigger = True
            
            current_statement += line + " "
            
            # Simple statement splitting for non-trigger statements
            if not in_trigger:
                if line.endswith(';'):
                    statements.append(current_statement.strip())
                    current_statement = ""
            else:
                # For triggers, look for END; pattern
                if line.upper().strip() == 'END;':
                    statements.append(current_statement.strip())
                    current_statement = ""
                    in_trigger = False
        
        if current_statement.strip():
            statements.append(current_statement.strip())
        
        return statements
    
    def _cleanup_temp_databases(self):
        """Clean up temporary database files (only called on error)."""
        for temp_db in self.temp_dbs:
            try:
                Path(temp_db).unlink(missing_ok=True)
            except Exception:
                pass  # Ignore cleanup errors
        self.temp_dbs.clear()