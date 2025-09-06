"""Migration analysis engine."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sqlparse
from sqlparse.sql import Statement, Token
from sqlparse.tokens import Keyword, Name

from .models import (
    MigrationFile, SqlStatement, StatementType, AlterOperation,
    TableOperation, SquashAnalysis
)


class MigrationAnalyzer:
    """Analyzes SQL migration files to detect patterns and optimization opportunities."""
    
    def __init__(self):
        self.backup_table_patterns = [
            r'CREATE\s+TABLE\s+(\w+)_backup',
            r'CREATE\s+TABLE\s+backup_(\w+)',
            r'CREATE\s+TABLE\s+(\w+)_temp',
            r'CREATE\s+TABLE\s+temp_(\w+)',
        ]
    
    def analyze_directory(self, migrations_dir: Path) -> SquashAnalysis:
        """Analyze all migration files in a directory."""
        if not migrations_dir.exists():
            raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")
        
        migration_files = self._load_migration_files(migrations_dir)
        table_operations = self._group_operations_by_table(migration_files)
        redundant_ops = self._identify_redundant_operations(table_operations)
        backup_patterns = self._detect_backup_patterns(migration_files)
        
        optimization_potential = len(redundant_ops)
        
        return SquashAnalysis(
            migrations=migration_files,
            table_operations=table_operations,
            redundant_operations=redundant_ops,
            backup_patterns=backup_patterns,
            optimization_potential=optimization_potential
        )
    
    def _load_migration_files(self, migrations_dir: Path) -> List[MigrationFile]:
        """Load and parse all migration files from directory."""
        migration_files = []
        
        # Find all .sql files and sort by name (assuming numeric prefixes)
        sql_files = sorted([f for f in migrations_dir.glob("*.sql")])
        
        for file_path in sql_files:
            sequence_num = self._extract_sequence_number(file_path.name)
            migration = MigrationFile(
                path=file_path,
                name=file_path.stem,
                sequence_number=sequence_num
            )
            
            migration.raw_content = file_path.read_text(encoding='utf-8')
            migration.statements = self._parse_sql_file(migration.raw_content)
            
            migration_files.append(migration)
        
        return migration_files
    
    def _extract_sequence_number(self, filename: str) -> int:
        """Extract sequence number from migration filename."""
        match = re.match(r'^(\d+)', filename)
        return int(match.group(1)) if match else 999999
    
    def _parse_sql_file(self, content: str) -> List[SqlStatement]:
        """Parse SQL content into structured statements."""
        statements = []
        
        # Remove comments and normalize whitespace
        content = self._clean_sql(content)
        
        # Parse with sqlparse
        parsed = sqlparse.parse(content)
        
        for stmt in parsed:
            if stmt.ttype is None and str(stmt).strip():  # Skip empty statements
                sql_stmt = self._analyze_statement(stmt)
                if sql_stmt:
                    statements.append(sql_stmt)
        
        return statements
    
    def _clean_sql(self, content: str) -> str:
        """Clean SQL content by removing comments and normalizing."""
        # Remove SQL comments (-- style)
        content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
        
        # Remove /* */ style comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Normalize whitespace but preserve line breaks for statement separation
        content = re.sub(r'[ \t]+', ' ', content)
        
        return content.strip()
    
    def _analyze_statement(self, stmt: Statement) -> Optional[SqlStatement]:
        """Analyze a parsed SQL statement to extract metadata."""
        stmt_str = str(stmt).strip()
        if not stmt_str:
            return None
        
        stmt_upper = stmt_str.upper()
        
        # Determine statement type and extract table name
        if stmt_upper.startswith('CREATE VIRTUAL TABLE'):
            return self._parse_create_virtual_table(stmt_str)
        elif stmt_upper.startswith('CREATE TABLE'):
            return self._parse_create_table(stmt_str)
        elif stmt_upper.startswith('ALTER TABLE'):
            return self._parse_alter_table(stmt_str)
        elif stmt_upper.startswith('DROP TABLE'):
            return self._parse_drop_table(stmt_str)
        elif stmt_upper.startswith('CREATE INDEX') or stmt_upper.startswith('CREATE UNIQUE INDEX'):
            return self._parse_create_index(stmt_str)
        elif stmt_upper.startswith('DROP INDEX'):
            return self._parse_drop_index(stmt_str)
        elif stmt_upper.startswith('CREATE TRIGGER'):
            return self._parse_create_trigger(stmt_str)
        elif stmt_upper.startswith('DROP TRIGGER'):
            return self._parse_drop_trigger(stmt_str)
        elif stmt_upper.startswith('INSERT'):
            return self._parse_insert(stmt_str)
        elif stmt_upper.startswith('UPDATE'):
            return self._parse_update(stmt_str)
        elif stmt_upper.startswith('DELETE'):
            return self._parse_delete(stmt_str)
        elif stmt_upper.startswith('PRAGMA'):
            return SqlStatement(
                type=StatementType.PRAGMA,
                table_name=None,
                raw_sql=stmt_str
            )
        else:
            return SqlStatement(
                type=StatementType.UNKNOWN,
                table_name=None,
                raw_sql=stmt_str
            )
    
    def _parse_create_table(self, stmt: str) -> SqlStatement:
        """Parse CREATE TABLE statement."""
        match = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.CREATE_TABLE,
            table_name=table_name,
            raw_sql=stmt
        )
    
    def _parse_create_virtual_table(self, stmt: str) -> SqlStatement:
        """Parse CREATE VIRTUAL TABLE statement."""
        match = re.search(r'CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.CREATE_VIRTUAL_TABLE,
            table_name=table_name,
            raw_sql=stmt
        )
    
    def _parse_create_trigger(self, stmt: str) -> SqlStatement:
        """Parse CREATE TRIGGER statement."""
        # Extract trigger name and table name
        trigger_match = re.search(r'CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_match = re.search(r'ON\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        
        trigger_name = trigger_match.group(1) if trigger_match else None
        table_name = table_match.group(1) if table_match else None
        
        return SqlStatement(
            type=StatementType.CREATE_TRIGGER,
            table_name=table_name,
            raw_sql=stmt,
            metadata={'trigger_name': trigger_name}
        )
    
    def _parse_drop_trigger(self, stmt: str) -> SqlStatement:
        """Parse DROP TRIGGER statement."""
        match = re.search(r'DROP\s+TRIGGER\s+(?:IF\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        trigger_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.DROP_TRIGGER,
            table_name=None,  # Triggers don't specify table in DROP
            raw_sql=stmt,
            metadata={'trigger_name': trigger_name}
        )
    
    def _parse_alter_table(self, stmt: str) -> SqlStatement:
        """Parse ALTER TABLE statement."""
        # Extract table name
        table_match = re.search(r'ALTER\s+TABLE\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = table_match.group(1) if table_match else None
        
        # Determine alter operation
        alter_op = AlterOperation.UNKNOWN
        column_name = None
        
        if re.search(r'ADD\s+COLUMN', stmt, re.IGNORECASE):
            alter_op = AlterOperation.ADD_COLUMN
            col_match = re.search(r'ADD\s+COLUMN\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
            column_name = col_match.group(1) if col_match else None
        elif re.search(r'DROP\s+COLUMN', stmt, re.IGNORECASE):
            alter_op = AlterOperation.DROP_COLUMN
            col_match = re.search(r'DROP\s+COLUMN\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
            column_name = col_match.group(1) if col_match else None
        elif re.search(r'RENAME\s+COLUMN', stmt, re.IGNORECASE):
            alter_op = AlterOperation.RENAME_COLUMN
        elif re.search(r'RENAME\s+TO', stmt, re.IGNORECASE):
            alter_op = AlterOperation.RENAME_TABLE
        
        return SqlStatement(
            type=StatementType.ALTER_TABLE,
            table_name=table_name,
            raw_sql=stmt,
            alter_operation=alter_op,
            column_name=column_name
        )
    
    def _parse_drop_table(self, stmt: str) -> SqlStatement:
        """Parse DROP TABLE statement."""
        match = re.search(r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.DROP_TABLE,
            table_name=table_name,
            raw_sql=stmt
        )
    
    def _parse_create_index(self, stmt: str) -> SqlStatement:
        """Parse CREATE INDEX statement."""
        # Extract index name and table name
        index_match = re.search(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_match = re.search(r'ON\s+(["`]?\w+["`]?)\s*\(', stmt, re.IGNORECASE)
        
        index_name = index_match.group(1) if index_match else None
        if table_match:
            table_name = table_match.group(1).strip('\'""`')
        else:
            table_name = None
        
        return SqlStatement(
            type=StatementType.CREATE_INDEX,
            table_name=table_name,
            raw_sql=stmt,
            index_name=index_name
        )
    
    def _parse_drop_index(self, stmt: str) -> SqlStatement:
        """Parse DROP INDEX statement."""
        match = re.search(r'DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        index_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.DROP_INDEX,
            table_name=None,  # DROP INDEX doesn't specify table in SQLite
            raw_sql=stmt,
            index_name=index_name
        )
    
    def _parse_insert(self, stmt: str) -> SqlStatement:
        """Parse INSERT statement."""
        match = re.search(r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.INSERT,
            table_name=table_name,
            raw_sql=stmt
        )
    
    def _parse_update(self, stmt: str) -> SqlStatement:
        """Parse UPDATE statement."""
        match = re.search(r'UPDATE\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.UPDATE,
            table_name=table_name,
            raw_sql=stmt
        )
    
    def _parse_delete(self, stmt: str) -> SqlStatement:
        """Parse DELETE statement."""
        match = re.search(r'DELETE\s+FROM\s+["`]?(\w+)["`]?', stmt, re.IGNORECASE)
        table_name = match.group(1) if match else None
        
        return SqlStatement(
            type=StatementType.DELETE,
            table_name=table_name,
            raw_sql=stmt
        )
    
    def _group_operations_by_table(self, migrations: List[MigrationFile]) -> Dict[str, TableOperation]:
        """Group all operations by table name."""
        table_ops = {}
        
        for migration in migrations:
            for stmt in migration.statements:
                if not stmt.table_name:
                    continue
                
                table_name = stmt.table_name
                if table_name not in table_ops:
                    table_ops[table_name] = TableOperation(table_name=table_name)
                
                table_op = table_ops[table_name]
                
                if stmt.type == StatementType.CREATE_TABLE:
                    table_op.create_statements.append(stmt)
                elif stmt.type == StatementType.CREATE_VIRTUAL_TABLE:
                    table_op.virtual_table_statements.append(stmt)
                elif stmt.type == StatementType.ALTER_TABLE:
                    table_op.alter_statements.append(stmt)
                elif stmt.type == StatementType.DROP_TABLE:
                    table_op.drop_statements.append(stmt)
                elif stmt.type in (StatementType.CREATE_INDEX, StatementType.DROP_INDEX):
                    table_op.index_statements.append(stmt)
                elif stmt.type in (StatementType.CREATE_TRIGGER, StatementType.DROP_TRIGGER):
                    table_op.trigger_statements.append(stmt)
        
        return table_ops
    
    def _identify_redundant_operations(self, table_ops: Dict[str, TableOperation]) -> List[SqlStatement]:
        """Identify redundant operations across all tables."""
        redundant = []
        
        for table_name, ops in table_ops.items():
            # Find redundant ALTER statements on same columns
            redundant.extend(ops.redundant_alters)
            
            # Find tables that are created and dropped (intermediate states)
            if len(ops.create_statements) > 1:
                # Keep only the last CREATE statement
                redundant.extend(ops.create_statements[:-1])
            
            # Find duplicate index creations
            index_names = set()
            for stmt in ops.index_statements:
                if stmt.type == StatementType.CREATE_INDEX and stmt.index_name:
                    if stmt.index_name in index_names:
                        redundant.append(stmt)
                    else:
                        index_names.add(stmt.index_name)
        
        return redundant
    
    def _detect_backup_patterns(self, migrations: List[MigrationFile]) -> List[str]:
        """Detect backup table patterns common in SQLite migrations."""
        backup_patterns = []
        
        for migration in migrations:
            for stmt in migration.statements:
                if stmt.type == StatementType.CREATE_TABLE and stmt.table_name:
                    for pattern in self.backup_table_patterns:
                        if re.search(pattern, stmt.raw_sql, re.IGNORECASE):
                            backup_patterns.append(f"{migration.name}: {stmt.table_name}")
                            break
        
        return backup_patterns