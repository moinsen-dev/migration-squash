"""Data models for migration analysis."""

from enum import Enum
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from pathlib import Path


class StatementType(Enum):
    """Types of SQL statements in migrations."""
    CREATE_TABLE = "CREATE_TABLE"
    CREATE_VIRTUAL_TABLE = "CREATE_VIRTUAL_TABLE"
    ALTER_TABLE = "ALTER_TABLE" 
    DROP_TABLE = "DROP_TABLE"
    CREATE_INDEX = "CREATE_INDEX"
    DROP_INDEX = "DROP_INDEX"
    CREATE_TRIGGER = "CREATE_TRIGGER"
    DROP_TRIGGER = "DROP_TRIGGER"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PRAGMA = "PRAGMA"
    UNKNOWN = "UNKNOWN"


class AlterOperation(Enum):
    """Types of ALTER TABLE operations."""
    ADD_COLUMN = "ADD_COLUMN"
    DROP_COLUMN = "DROP_COLUMN"
    RENAME_COLUMN = "RENAME_COLUMN"
    RENAME_TABLE = "RENAME_TABLE"
    ADD_CONSTRAINT = "ADD_CONSTRAINT"
    DROP_CONSTRAINT = "DROP_CONSTRAINT"
    UNKNOWN = "UNKNOWN"


@dataclass
class SqlStatement:
    """Represents a parsed SQL statement."""
    type: StatementType
    table_name: Optional[str]
    raw_sql: str
    alter_operation: Optional[AlterOperation] = None
    column_name: Optional[str] = None
    index_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationFile:
    """Represents a single migration file."""
    path: Path
    name: str
    sequence_number: int
    statements: List[SqlStatement] = field(default_factory=list)
    raw_content: str = ""
    
    @property
    def tables_affected(self) -> Set[str]:
        """Get all table names affected by this migration."""
        tables = set()
        for stmt in self.statements:
            if stmt.table_name:
                tables.add(stmt.table_name)
        return tables


@dataclass
class TableOperation:
    """Represents operations on a specific table across migrations."""
    table_name: str
    create_statements: List[SqlStatement] = field(default_factory=list)
    virtual_table_statements: List[SqlStatement] = field(default_factory=list)
    alter_statements: List[SqlStatement] = field(default_factory=list)
    drop_statements: List[SqlStatement] = field(default_factory=list)
    index_statements: List[SqlStatement] = field(default_factory=list)
    trigger_statements: List[SqlStatement] = field(default_factory=list)
    
    @property
    def has_create_drop_cycle(self) -> bool:
        """Check if table is created and dropped multiple times."""
        return len(self.create_statements) > 1 or len(self.drop_statements) > 0
    
    @property
    def redundant_alters(self) -> List[SqlStatement]:
        """Find ALTER statements that might be redundant."""
        redundant = []
        seen_columns = set()
        
        for alter in reversed(self.alter_statements):
            if alter.column_name:
                if alter.column_name in seen_columns:
                    redundant.append(alter)
                else:
                    seen_columns.add(alter.column_name)
        
        return list(reversed(redundant))


@dataclass
class SquashAnalysis:
    """Results of migration analysis for squashing."""
    migrations: List[MigrationFile]
    table_operations: Dict[str, TableOperation]
    redundant_operations: List[SqlStatement] = field(default_factory=list)
    backup_patterns: List[str] = field(default_factory=list)
    optimization_potential: int = 0
    
    @property
    def total_statements(self) -> int:
        """Total number of SQL statements across all migrations."""
        return sum(len(mig.statements) for mig in self.migrations)
    
    @property
    def tables_with_issues(self) -> List[str]:
        """Tables that have redundant or problematic operations."""
        problematic = []
        for table_name, ops in self.table_operations.items():
            if ops.has_create_drop_cycle or ops.redundant_alters:
                problematic.append(table_name)
        return problematic


@dataclass
class SquashResult:
    """Result of migration squashing operation."""
    original_files: int
    squashed_files: int
    statements_reduced: int
    schema_sql: str
    data_sql: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)