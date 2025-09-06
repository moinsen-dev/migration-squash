"""Tests for migration squasher."""

import pytest
from src.squasher import MigrationSquasher, SquashConfig
from src.analyzer import MigrationAnalyzer
from src.models import SqlStatement, StatementType, AlterOperation, TableOperation, SquashAnalysis


class TestMigrationSquasher:
    
    def test_squash_config_defaults(self):
        """Test default squash configuration."""
        config = SquashConfig()
        assert config.group_by == "table"
        assert config.keep_data_separate is True
        assert config.preserve_comments is False
        
    def test_merge_alters_into_create(self):
        """Test merging ALTER TABLE operations into CREATE TABLE."""
        squasher = MigrationSquasher()
        
        create_stmt = SqlStatement(
            type=StatementType.CREATE_TABLE,
            table_name="users",
            raw_sql="CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
        )
        
        alter_stmt = SqlStatement(
            type=StatementType.ALTER_TABLE,
            table_name="users", 
            raw_sql="ALTER TABLE users ADD COLUMN age INTEGER;",
            alter_operation=AlterOperation.ADD_COLUMN,
            column_name="age"
        )
        
        merged = squasher._merge_alters_into_create(create_stmt, [alter_stmt])
        
        assert "age INTEGER" in merged.raw_sql
        assert merged.metadata.get('merged_alters') == 1
        
    def test_remove_redundant_alters(self):
        """Test removal of redundant ALTER operations."""
        squasher = MigrationSquasher()
        
        alters = [
            SqlStatement(
                type=StatementType.ALTER_TABLE,
                table_name="users",
                raw_sql="ALTER TABLE users ADD COLUMN age INTEGER;",
                alter_operation=AlterOperation.ADD_COLUMN,
                column_name="age"
            ),
            SqlStatement(
                type=StatementType.ALTER_TABLE, 
                table_name="users",
                raw_sql="ALTER TABLE users DROP COLUMN age;",
                alter_operation=AlterOperation.DROP_COLUMN,
                column_name="age"
            ),
            SqlStatement(
                type=StatementType.ALTER_TABLE,
                table_name="users", 
                raw_sql="ALTER TABLE users ADD COLUMN age INTEGER DEFAULT 0;",
                alter_operation=AlterOperation.ADD_COLUMN,
                column_name="age"
            )
        ]
        
        non_redundant = squasher._remove_redundant_alters(alters)
        
        # Should keep only the last operation on 'age' column
        assert len(non_redundant) == 1
        assert non_redundant[0].raw_sql == "ALTER TABLE users ADD COLUMN age INTEGER DEFAULT 0;"
        
    def test_optimize_index_statements(self):
        """Test optimization of index statements."""
        squasher = MigrationSquasher()
        
        index_stmts = [
            SqlStatement(
                type=StatementType.CREATE_INDEX,
                table_name="users",
                raw_sql="CREATE INDEX idx_users_email ON users(email);",
                index_name="idx_users_email"
            ),
            SqlStatement(
                type=StatementType.DROP_INDEX,
                table_name=None,
                raw_sql="DROP INDEX idx_users_email;",
                index_name="idx_users_email"
            ),
            SqlStatement(
                type=StatementType.CREATE_INDEX,
                table_name="users",
                raw_sql="CREATE UNIQUE INDEX idx_users_email ON users(email);",
                index_name="idx_users_email"
            )
        ]
        
        optimized = squasher._optimize_index_statements(index_stmts)
        
        # Should keep only the final CREATE INDEX
        assert len(optimized) == 1
        assert "UNIQUE" in optimized[0].raw_sql
        
    def test_is_data_statement(self):
        """Test data statement identification."""
        squasher = MigrationSquasher()
        
        insert_stmt = SqlStatement(type=StatementType.INSERT, table_name="users", raw_sql="INSERT INTO users ...")
        create_stmt = SqlStatement(type=StatementType.CREATE_TABLE, table_name="users", raw_sql="CREATE TABLE ...")
        
        assert squasher._is_data_statement(insert_stmt) is True
        assert squasher._is_data_statement(create_stmt) is False
        
    def test_generate_sql_formatting(self):
        """Test SQL generation and formatting."""
        squasher = MigrationSquasher()
        
        statements = [
            SqlStatement(
                type=StatementType.CREATE_TABLE,
                table_name="users",
                raw_sql="CREATE TABLE users (id INTEGER PRIMARY KEY);"
            ),
            SqlStatement(
                type=StatementType.CREATE_INDEX, 
                table_name="users",
                raw_sql="CREATE INDEX idx_users_id ON users(id);",
                index_name="idx_users_id"
            )
        ]
        
        sql = squasher._generate_sql(statements, "Test Migration")
        
        assert "Test Migration" in sql
        assert "Table: users" in sql
        assert "CREATE TABLE users" in sql
        assert "CREATE INDEX idx_users_id" in sql