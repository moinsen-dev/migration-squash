"""Tests for migration validator."""

import pytest
import tempfile
import sqlite3
from pathlib import Path

from src.validator import MigrationValidator, SafetyChecker
from src.models import SqlStatement, StatementType


class TestMigrationValidator:
    
    def test_split_sql_statements(self):
        """Test SQL statement splitting."""
        validator = MigrationValidator()
        
        sql = """
        CREATE TABLE users (id INTEGER PRIMARY KEY);
        INSERT INTO users (id) VALUES (1);
        CREATE INDEX idx_users ON users(id);
        """
        
        statements = validator._split_sql_statements(sql)
        
        assert len(statements) >= 3
        assert any("CREATE TABLE" in stmt for stmt in statements)
        assert any("INSERT INTO" in stmt for stmt in statements)
        
    def test_extract_database_schema(self):
        """Test database schema extraction."""
        validator = MigrationValidator()
        
        # Create temporary database with test schema
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
            conn = sqlite3.connect(temp_db.name)
            conn.row_factory = sqlite3.Row
            
            # Create test schema
            conn.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE
                );
            """)
            
            conn.execute("CREATE INDEX idx_users_email ON users(email);")
            conn.commit()
            
            # Extract schema
            schema = validator._extract_database_schema(conn)
            
            # Verify extracted schema
            assert 'users' in schema['tables']
            assert 'idx_users_email' in schema['indexes']
            
            user_table = schema['tables']['users']
            assert 'id' in user_table['columns']
            assert 'name' in user_table['columns']
            assert 'email' in user_table['columns']
            
            # Check column properties
            id_col = user_table['columns']['id']
            assert id_col['type'] == 'INTEGER'
            assert id_col['pk'] is True
            
            name_col = user_table['columns']['name']
            assert name_col['notnull'] is True
            
            conn.close()
            
            # Cleanup
            Path(temp_db.name).unlink()
            
    def test_compare_table_columns(self):
        """Test table column comparison."""
        validator = MigrationValidator()
        
        original_cols = {
            'id': {'type': 'INTEGER', 'notnull': False, 'default': None, 'pk': True},
            'name': {'type': 'TEXT', 'notnull': True, 'default': None, 'pk': False}
        }
        
        squashed_cols = {
            'id': {'type': 'INTEGER', 'notnull': False, 'default': None, 'pk': True},
            'name': {'type': 'TEXT', 'notnull': True, 'default': None, 'pk': False}
        }
        
        differences = []
        result = validator._compare_table_columns('users', original_cols, squashed_cols, differences)
        
        assert result is True
        assert len(differences) == 0
        
    def test_compare_table_columns_mismatch(self):
        """Test table column comparison with mismatches."""
        validator = MigrationValidator()
        
        original_cols = {
            'id': {'type': 'INTEGER', 'notnull': False, 'default': None, 'pk': True},
            'name': {'type': 'TEXT', 'notnull': True, 'default': None, 'pk': False}
        }
        
        squashed_cols = {
            'id': {'type': 'INTEGER', 'notnull': False, 'default': None, 'pk': True},
            'name': {'type': 'VARCHAR', 'notnull': True, 'default': None, 'pk': False}  # Different type
        }
        
        differences = []
        result = validator._compare_table_columns('users', original_cols, squashed_cols, differences)
        
        assert result is False
        assert len(differences) > 0


class TestSafetyChecker:
    
    def test_check_migrations_safety_safe(self):
        """Test safety checks on safe migrations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir) / "migrations"
            migrations_dir.mkdir()
            
            # Safe migration
            (migrations_dir / "001_create_table.sql").write_text("""
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            """)
            
            (migrations_dir / "002_add_column.sql").write_text("""
                ALTER TABLE users ADD COLUMN email TEXT;
            """)
            
            checker = SafetyChecker()
            checks = checker.check_migrations_safety(migrations_dir)
            
            assert checks['safe_to_squash'] is True
            assert checks['data_loss_risk'] is False
            assert len(checks['destructive_operations']) == 0
            
    def test_check_migrations_safety_destructive(self):
        """Test safety checks on destructive migrations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir) / "migrations"
            migrations_dir.mkdir()
            
            # Destructive migration
            (migrations_dir / "001_drop_table.sql").write_text("""
                DROP TABLE old_users;
            """)
            
            (migrations_dir / "002_delete_data.sql").write_text("""
                DELETE FROM users WHERE created_at < '2020-01-01';
            """)
            
            checker = SafetyChecker()
            checks = checker.check_migrations_safety(migrations_dir)
            
            assert checks['data_loss_risk'] is True
            assert len(checks['destructive_operations']) > 0
            assert len(checks['warnings']) > 0
            
    def test_check_migrations_safety_with_backup(self):
        """Test safety checks on destructive migrations with backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir) / "migrations"
            migrations_dir.mkdir()
            
            # Migration with backup pattern
            (migrations_dir / "001_with_backup.sql").write_text("""
                CREATE TABLE users_backup AS SELECT * FROM users;
                DROP TABLE users;
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);
                INSERT INTO users SELECT id, name, NULL FROM users_backup;
                DROP TABLE users_backup;
            """)
            
            checker = SafetyChecker()
            checks = checker.check_migrations_safety(migrations_dir)
            
            assert checks['has_backup'] is True
            # Even with destructive operations, backup patterns make it safer
            assert checks['safe_to_squash'] is True