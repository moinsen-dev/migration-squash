"""Smart migration squashing engine."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from .models import (
    MigrationFile, SqlStatement, StatementType, AlterOperation,
    TableOperation, SquashAnalysis, SquashResult
)


@dataclass
class SquashConfig:
    """Configuration for squashing operations."""
    group_by: str = "table"  # "table", "feature", "date"
    keep_data_separate: bool = True
    preserve_comments: bool = False
    output_format: str = "single"  # "single", "grouped", "minimal"


class MigrationSquasher:
    """Intelligently squashes migration files by eliminating redundancy."""
    
    def __init__(self, config: SquashConfig = None):
        self.config = config or SquashConfig()
        self.known_migration_tables = {
            'migrations', 'alembic_version', 'django_migrations',
            'schema_migrations', 'flyway_schema_history', 'knex_migrations',
            'knex_migrations_lock', 'goose_db_version', 'drizzle__migrations'
        }
        self.backup_table_patterns = [
            r'.*_backup$', r'^backup_.*', r'.*_temp$', r'^temp_.*',
            r'.*_old$', r'^old_.*', r'.*_tmp$', r'^tmp_.*',
            r'.*_final$', r'^final_.*'
        ]
    
    def squash(self, analysis: SquashAnalysis) -> SquashResult:
        """Squash migrations based on analysis results."""
        schema_statements = []
        data_statements = []
        
        # Process each table to generate optimized statements
        for table_name, ops in analysis.table_operations.items():
            if table_name.lower() in self.known_migration_tables:
                continue  # Skip migration tracking tables
            
            if self._is_backup_table(table_name):
                continue  # Skip backup tables
            
            optimized = self._optimize_table_operations(table_name, ops)
            
            for stmt in optimized:
                if self._is_data_statement(stmt):
                    data_statements.append(stmt)
                else:
                    schema_statements.append(stmt)
        
        # Generate final SQL
        schema_sql = self._generate_sql(schema_statements, "Schema Migration")
        data_sql = self._generate_sql(data_statements, "Data Migration") if data_statements else None
        
        statements_reduced = analysis.total_statements - len(schema_statements) - len(data_statements)
        
        return SquashResult(
            original_files=len(analysis.migrations),
            squashed_files=1 if not data_sql else 2,
            statements_reduced=statements_reduced,
            schema_sql=schema_sql,
            data_sql=data_sql,
            metadata={
                'optimization_potential': analysis.optimization_potential,
                'tables_processed': len(analysis.table_operations),
                'backup_patterns_found': len(analysis.backup_patterns)
            }
        )
    
    def _optimize_table_operations(self, table_name: str, ops: TableOperation) -> List[SqlStatement]:
        """Optimize operations for a single table."""
        optimized = []
        
        # Handle CREATE-DROP-CREATE cycles
        if ops.has_create_drop_cycle:
            # Use the final CREATE statement and merge all relevant ALTERs
            final_create = self._resolve_create_statements_with_alters(ops.create_statements, ops.alter_statements)
            if final_create:
                optimized.append(final_create)
        elif ops.create_statements:
            # No cycles, use first CREATE and merge ALTERs
            base_create = ops.create_statements[0]
            merged_create = self._merge_alters_into_create(base_create, ops.alter_statements)
            optimized.append(merged_create)
        
        # Add non-redundant ALTER statements not merged into CREATE
        # Skip this for CREATE/DROP cycles since ALTERs are already merged into the final CREATE
        if not ops.has_create_drop_cycle and (not ops.create_statements or not self._can_merge_alters(ops.alter_statements)):
            non_redundant_alters = self._remove_redundant_alters(ops.alter_statements)
            optimized.extend(non_redundant_alters)
        
        # Add virtual table statements (FTS, etc.)
        optimized.extend(ops.virtual_table_statements)
        
        # Add optimized index statements
        optimized_indexes = self._optimize_index_statements(ops.index_statements)
        optimized.extend(optimized_indexes)
        
        # Add trigger statements
        optimized.extend(ops.trigger_statements)
        
        return optimized
    
    def _resolve_create_statements(self, creates: List[SqlStatement]) -> Optional[SqlStatement]:
        """Resolve multiple CREATE statements to the most complete one."""
        if not creates:
            return None
        
        # For now, use the last CREATE statement (most recent)
        # TODO: In future, could analyze and merge column definitions
        return creates[-1]
    
    def _resolve_create_statements_with_alters(self, creates: List[SqlStatement], alters: List[SqlStatement]) -> Optional[SqlStatement]:
        """Resolve CREATE statements with ALTER operations for CREATE/DROP cycles.
        
        This method handles the case where we have CREATE/DROP cycles and need to merge
        ALTER statements that occurred after the DROP into the final CREATE statement.
        """
        if not creates:
            return None
        
        # Use the last (final) CREATE statement as the base
        final_create = creates[-1]
        
        # For CREATE/DROP cycles, we need to merge ALL ALTER statements
        # because they represent the complete evolution of the table schema
        merged_create = self._merge_alters_into_create(final_create, alters)
        
        return merged_create
    
    def _merge_alters_into_create(self, create_stmt: SqlStatement, alters: List[SqlStatement]) -> SqlStatement:
        """Merge ALTER TABLE operations into the CREATE TABLE statement."""
        if not alters or not self._can_merge_alters(alters):
            return create_stmt
        
        create_sql = create_stmt.raw_sql
        
        # Extract table definition
        match = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^(]+)\s*\((.*)\)', create_sql, re.IGNORECASE | re.DOTALL)
        if not match:
            return create_stmt  # Can't parse, return original
        
        table_part = match.group(1).strip()
        table_content = match.group(2).strip()
        
        # Process ADD COLUMN operations
        additional_columns = []
        for alter in alters:
            if alter.alter_operation == AlterOperation.ADD_COLUMN:
                # Extract column definition from ALTER statement
                col_match = re.search(r'ADD\s+COLUMN\s+(.+)(?:;|$)', alter.raw_sql, re.IGNORECASE)
                if col_match:
                    col_def = col_match.group(1).strip()
                    # Remove trailing semicolons and commas from column definition
                    col_def = col_def.rstrip(';,')
                    additional_columns.append(col_def)
        
        if additional_columns:
            # Parse the table content to separate columns from constraints
            table_content = table_content.rstrip()
            
            # Split by commas but need to handle multi-line constructs carefully
            # Use a simple regex to find top-level comma-separated items
            items = []
            current_item = ""
            paren_depth = 0
            
            for char in table_content:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                elif char == ',' and paren_depth == 0:
                    # This is a top-level comma separator
                    if current_item.strip():
                        items.append(current_item.strip())
                    current_item = ""
                    continue
                    
                current_item += char
            
            # Add the last item
            if current_item.strip():
                items.append(current_item.strip())
            
            # Now classify each item as column or constraint
            columns = []
            constraints = []
            
            for item in items:
                item_clean = item.strip()
                
                # Check if this is a constraint (FOREIGN KEY, UNIQUE, CHECK, PRIMARY KEY, etc.)
                item_upper = item_clean.upper()
                if (item_upper.startswith('FOREIGN KEY') or 
                    item_upper.startswith('CONSTRAINT') or
                    item_upper.startswith('CHECK') or
                    item_upper.startswith('UNIQUE') or
                    (item_upper.startswith('PRIMARY KEY') and not item_clean.split()[0].upper().endswith('PRIMARY'))):
                    constraints.append(item_clean)
                else:
                    columns.append(item_clean)
            
            # Add the additional columns to the column list
            columns.extend(additional_columns)
            
            # Reconstruct the table content: columns first, then constraints
            all_items = columns + constraints
            
            # Format with proper commas - all items except the last get commas
            formatted_items = []
            for i, item in enumerate(all_items):
                if i == len(all_items) - 1:
                    # Last item - no trailing comma
                    formatted_items.append(item)
                else:
                    # All other items - add trailing comma
                    formatted_items.append(item + ',')
            
            merged_content = '\n  '.join(formatted_items)
            merged_sql = f"CREATE TABLE IF NOT EXISTS {table_part} (\n  {merged_content}\n);"
            
            return SqlStatement(
                type=StatementType.CREATE_TABLE,
                table_name=create_stmt.table_name,
                raw_sql=merged_sql,
                metadata={'merged_alters': len(additional_columns)}
            )
        
        return create_stmt
    
    def _can_merge_alters(self, alters: List[SqlStatement]) -> bool:
        """Check if ALTER statements can be merged into CREATE."""
        # Only merge ADD COLUMN operations for now
        return all(
            alter.alter_operation == AlterOperation.ADD_COLUMN 
            for alter in alters
        )
    
    def _remove_redundant_alters(self, alters: List[SqlStatement]) -> List[SqlStatement]:
        """Remove redundant ALTER operations."""
        if not alters:
            return []
        
        # Group by column name to find redundant operations
        column_operations = {}
        
        for alter in alters:
            if not alter.column_name:
                continue
            
            col_name = alter.column_name
            if col_name not in column_operations:
                column_operations[col_name] = []
            column_operations[col_name].append(alter)
        
        # Keep only the last operation per column
        non_redundant = []
        for alter in alters:
            if not alter.column_name:
                non_redundant.append(alter)  # Keep non-column operations
                continue
            
            col_ops = column_operations[alter.column_name]
            if alter == col_ops[-1]:  # Keep only last operation per column
                non_redundant.append(alter)
        
        return non_redundant
    
    def _optimize_index_statements(self, index_stmts: List[SqlStatement]) -> List[SqlStatement]:
        """Optimize index creation/deletion statements."""
        if not index_stmts:
            return []
        
        # Group by index name
        index_ops = {}
        
        for stmt in index_stmts:
            if not stmt.index_name:
                continue
            
            idx_name = stmt.index_name
            if idx_name not in index_ops:
                index_ops[idx_name] = []
            index_ops[idx_name].append(stmt)
        
        # Keep only final state of each index
        optimized = []
        for idx_name, ops in index_ops.items():
            if ops:
                last_op = ops[-1]
                # Only keep CREATE INDEX statements (ignore DROP if it's the last operation)
                if last_op.type == StatementType.CREATE_INDEX:
                    optimized.append(last_op)
        
        return optimized
    
    def _is_backup_table(self, table_name: str) -> bool:
        """Check if table name matches backup table patterns."""
        import re
        for pattern in self.backup_table_patterns:
            if re.match(pattern, table_name, re.IGNORECASE):
                return True
        return False
    
    def _is_data_statement(self, stmt: SqlStatement) -> bool:
        """Check if statement is data manipulation (INSERT/UPDATE/DELETE)."""
        return stmt.type in (StatementType.INSERT, StatementType.UPDATE, StatementType.DELETE)
    
    def _generate_sql(self, statements: List[SqlStatement], title: str) -> str:
        """Generate final SQL from optimized statements."""
        if not statements:
            return ""
        
        lines = []
        lines.append(f"-- ==========================================")
        lines.append(f"-- {title}")
        lines.append(f"-- Generated by migration-squash tool")
        lines.append(f"-- Statements: {len(statements)}")
        lines.append(f"-- ==========================================")
        lines.append("")
        
        # Group statements by table for better organization
        table_statements = {}
        other_statements = []
        
        for stmt in statements:
            if stmt.table_name and stmt.table_name.strip() and stmt.table_name not in ['ON']:
                table_name = stmt.table_name
                if table_name not in table_statements:
                    table_statements[table_name] = []
                table_statements[table_name].append(stmt)
            else:
                other_statements.append(stmt)
        
        # Output CREATE TABLE statements first, then ALTERs, then INDEXes
        for table_name in sorted(table_statements.keys()):
            table_stmts = table_statements[table_name]
            
            lines.append(f"-- Table: {table_name}")
            
            # CREATE statements first (regular tables only - virtual tables come later)
            creates = [s for s in table_stmts if s.type == StatementType.CREATE_TABLE]
            
            for stmt in creates:
                lines.append(stmt.raw_sql)
                lines.append("")
            
            # ALTER statements
            alters = [s for s in table_stmts if s.type == StatementType.ALTER_TABLE]
            for stmt in alters:
                lines.append(stmt.raw_sql)
            
            if alters:
                lines.append("")
            
            # INDEX statements
            indexes = [s for s in table_stmts if s.type in (StatementType.CREATE_INDEX, StatementType.DROP_INDEX)]
            for stmt in indexes:
                lines.append(stmt.raw_sql)
            
            if indexes:
                lines.append("")
            
        # Add virtual tables after all regular tables are created
        lines.append("-- Virtual Tables")
        for table_name in sorted(table_statements.keys()):
            table_stmts = table_statements[table_name]
            virtual_creates = [s for s in table_stmts if s.type == StatementType.CREATE_VIRTUAL_TABLE]
            
            for stmt in virtual_creates:
                lines.append(stmt.raw_sql)
                lines.append("")
        
        # Add triggers after all tables and virtual tables are created  
        lines.append("-- Triggers")
        for table_name in sorted(table_statements.keys()):
            table_stmts = table_statements[table_name]
            triggers = [s for s in table_stmts if s.type in (StatementType.CREATE_TRIGGER, StatementType.DROP_TRIGGER)]
            
            for stmt in triggers:
                lines.append(stmt.raw_sql)
                lines.append("")
        
        # Other statements (PRAGMA, orphaned indexes, etc.)
        if other_statements:
            lines.append("-- Other Statements")
            for stmt in other_statements:
                lines.append(stmt.raw_sql)
            lines.append("")
        
        return "\n".join(lines)