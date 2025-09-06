"""SQLite-specific migration patterns and optimizations."""

import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

from .models import SqlStatement, StatementType, MigrationFile


@dataclass
class BackupTablePattern:
    """Represents a backup table migration pattern."""
    original_table: str
    backup_table: str
    operations: List[SqlStatement]
    migration_file: str


class SQLitePatternDetector:
    """Detects SQLite-specific migration patterns that can be optimized."""
    
    def __init__(self):
        self.backup_patterns = [
            r'(\w+)_backup',
            r'backup_(\w+)',
            r'(\w+)_temp',
            r'temp_(\w+)',
            r'(\w+)_old',
            r'old_(\w+)'
        ]
    
    def detect_backup_table_migrations(self, migrations: List[MigrationFile]) -> List[BackupTablePattern]:
        """Detect backup table patterns common in SQLite migrations.
        
        SQLite often requires creating backup tables for complex schema changes
        since it doesn't support many ALTER operations directly.
        """
        patterns = []
        
        for migration in migrations:
            backup_sequences = self._find_backup_sequences(migration)
            patterns.extend(backup_sequences)
        
        return patterns
    
    def _find_backup_sequences(self, migration: MigrationFile) -> List[BackupTablePattern]:
        """Find backup table sequences in a single migration."""
        sequences = []
        statements = migration.statements
        
        # Look for CREATE backup table patterns
        for i, stmt in enumerate(statements):
            if stmt.type != StatementType.CREATE_TABLE or not stmt.table_name:
                continue
            
            backup_match = self._is_backup_table(stmt.table_name)
            if backup_match:
                original_table = backup_match
                pattern = self._analyze_backup_sequence(statements, i, original_table, stmt.table_name)
                if pattern:
                    pattern.migration_file = migration.name
                    sequences.append(pattern)
        
        return sequences
    
    def _is_backup_table(self, table_name: str) -> Optional[str]:
        """Check if table name matches backup pattern and return original table name."""
        for pattern in self.backup_patterns:
            match = re.match(pattern, table_name, re.IGNORECASE)
            if match:
                return match.group(1) if match.group(1) else table_name.replace('backup_', '').replace('_backup', '')
        return None
    
    def _analyze_backup_sequence(self, statements: List[SqlStatement], start_idx: int, 
                                original_table: str, backup_table: str) -> Optional[BackupTablePattern]:
        """Analyze sequence of operations involving a backup table."""
        operations = []
        
        # Look ahead for operations on both tables
        for i in range(start_idx, len(statements)):
            stmt = statements[i]
            
            if stmt.table_name in (original_table, backup_table):
                operations.append(stmt)
                
                # Stop if we see DROP of backup table (end of sequence)
                if (stmt.type == StatementType.DROP_TABLE and 
                    stmt.table_name == backup_table):
                    break
        
        if len(operations) >= 3:  # Minimum: CREATE backup, operations, DROP backup
            return BackupTablePattern(
                original_table=original_table,
                backup_table=backup_table,
                operations=operations,
                migration_file=""  # Set by caller
            )
        
        return None


class SQLiteOptimizer:
    """Optimizes SQLite-specific migration patterns."""
    
    def optimize_backup_patterns(self, patterns: List[BackupTablePattern]) -> Dict[str, List[SqlStatement]]:
        """Convert backup table patterns into direct table modifications where possible."""
        optimized = {}
        
        for pattern in patterns:
            try:
                direct_operations = self._convert_backup_to_direct(pattern)
                if direct_operations:
                    optimized[pattern.original_table] = direct_operations
            except Exception:
                # If optimization fails, we'll keep the original pattern
                continue
        
        return optimized
    
    def _convert_backup_to_direct(self, pattern: BackupTablePattern) -> Optional[List[SqlStatement]]:
        """Convert backup table pattern to direct operations."""
        # Analyze the pattern to understand what changes are being made
        analysis = self._analyze_backup_operations(pattern)
        
        if not analysis:
            return None
        
        # Generate direct operations based on analysis
        direct_ops = []
        
        # If it's just adding columns, convert to ALTER TABLE ADD COLUMN
        if analysis['operation_type'] == 'add_columns':
            for column_def in analysis['added_columns']:
                alter_sql = f"ALTER TABLE {pattern.original_table} ADD COLUMN {column_def};"
                direct_ops.append(SqlStatement(
                    type=StatementType.ALTER_TABLE,
                    table_name=pattern.original_table,
                    raw_sql=alter_sql,
                    metadata={'optimized_from_backup': True}
                ))
        
        return direct_ops if direct_ops else None
    
    def _analyze_backup_operations(self, pattern: BackupTablePattern) -> Optional[Dict]:
        """Analyze what the backup pattern is actually doing."""
        # This is a simplified analysis - in a full implementation,
        # you would parse the CREATE TABLE statements to compare schemas
        
        create_backup = None
        insert_from_original = None
        drop_original = None
        rename_backup = None
        
        for op in pattern.operations:
            if op.type == StatementType.CREATE_TABLE and op.table_name == pattern.backup_table:
                create_backup = op
            elif op.type == StatementType.INSERT and op.table_name == pattern.backup_table:
                insert_from_original = op
            elif op.type == StatementType.DROP_TABLE and op.table_name == pattern.original_table:
                drop_original = op
            elif (op.type == StatementType.ALTER_TABLE and 
                  'RENAME TO' in op.raw_sql.upper() and 
                  pattern.backup_table in op.raw_sql):
                rename_backup = op
        
        if not all([create_backup, insert_from_original]):
            return None
        
        # Simple heuristic: if we're copying all data and just adding columns,
        # it's likely an ADD COLUMN operation
        if 'SELECT *' in insert_from_original.raw_sql:
            # Compare CREATE statements to find differences
            return {
                'operation_type': 'add_columns',
                'added_columns': self._extract_added_columns(create_backup.raw_sql)
            }
        
        return None
    
    def _extract_added_columns(self, create_sql: str) -> List[str]:
        """Extract added columns from CREATE TABLE statement (simplified)."""
        # This is a placeholder - in a real implementation, you would
        # parse both the original and backup CREATE statements to find differences
        return []
    
    def detect_redundant_indexes(self, statements: List[SqlStatement]) -> List[SqlStatement]:
        """Detect redundant index operations."""
        index_operations = {}
        redundant = []
        
        for stmt in statements:
            if stmt.type not in (StatementType.CREATE_INDEX, StatementType.DROP_INDEX):
                continue
            
            if not stmt.index_name:
                continue
            
            index_name = stmt.index_name
            if index_name not in index_operations:
                index_operations[index_name] = []
            index_operations[index_name].append(stmt)
        
        # Find redundant operations
        for index_name, ops in index_operations.items():
            if len(ops) > 1:
                # Keep only the last operation
                redundant.extend(ops[:-1])
        
        return redundant
    
    def optimize_pragma_statements(self, statements: List[SqlStatement]) -> List[SqlStatement]:
        """Optimize PRAGMA statements by removing duplicates."""
        seen_pragmas = set()
        optimized = []
        
        for stmt in statements:
            if stmt.type != StatementType.PRAGMA:
                optimized.append(stmt)
                continue
            
            # Extract PRAGMA name
            pragma_match = re.match(r'PRAGMA\s+(\w+)', stmt.raw_sql, re.IGNORECASE)
            if pragma_match:
                pragma_name = pragma_match.group(1).lower()
                if pragma_name not in seen_pragmas:
                    seen_pragmas.add(pragma_name)
                    optimized.append(stmt)
                # Skip duplicate PRAGMA
            else:
                optimized.append(stmt)  # Keep unknown PRAGMA format
        
        return optimized