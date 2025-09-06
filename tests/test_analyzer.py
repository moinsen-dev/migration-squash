"""Tests for migration analyzer."""

import pytest
import tempfile
from pathlib import Path

from src.analyzer import MigrationAnalyzer
from src.models import StatementType, AlterOperation


@pytest.fixture
def temp_migrations_dir():
    """Create temporary directory with sample migration files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        migrations_dir = Path(temp_dir) / "migrations"
        migrations_dir.mkdir()
        
        # Sample migration 1: Create table
        (migrations_dir / "001_create_users.sql").write_text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            );
        """)
        
        # Sample migration 2: Add column
        (migrations_dir / "002_add_user_age.sql").write_text("""
            ALTER TABLE users ADD COLUMN age INTEGER;
        """)
        
        # Sample migration 3: Fix the age column (redundant)
        (migrations_dir / "003_fix_user_age.sql").write_text("""
            ALTER TABLE users DROP COLUMN age;
            ALTER TABLE users ADD COLUMN age INTEGER DEFAULT 0;
        """)
        
        # Sample migration 4: Create index
        (migrations_dir / "004_add_user_email_index.sql").write_text("""
            CREATE INDEX idx_users_email ON users(email);
        """)
        
        yield migrations_dir


class TestMigrationAnalyzer:
    
    def test_analyze_directory(self, temp_migrations_dir):
        """Test analyzing a directory of migrations."""
        analyzer = MigrationAnalyzer()
        analysis = analyzer.analyze_directory(temp_migrations_dir)
        
        assert len(analysis.migrations) == 4
        assert len(analysis.table_operations) >= 1
        assert 'users' in analysis.table_operations
        
    def test_load_migration_files(self, temp_migrations_dir):
        """Test loading migration files."""
        analyzer = MigrationAnalyzer()
        migrations = analyzer._load_migration_files(temp_migrations_dir)
        
        assert len(migrations) == 4
        assert migrations[0].name == "001_create_users"
        assert migrations[0].sequence_number == 1
        
    def test_parse_create_table(self):
        """Test parsing CREATE TABLE statement."""
        analyzer = MigrationAnalyzer()
        sql = "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
        stmt = analyzer._parse_create_table(sql)
        
        assert stmt.type == StatementType.CREATE_TABLE
        assert stmt.table_name == "users"
        assert stmt.raw_sql == sql
        
    def test_parse_alter_table(self):
        """Test parsing ALTER TABLE statement."""
        analyzer = MigrationAnalyzer()
        sql = "ALTER TABLE users ADD COLUMN age INTEGER;"
        stmt = analyzer._parse_alter_table(sql)
        
        assert stmt.type == StatementType.ALTER_TABLE
        assert stmt.table_name == "users"
        assert stmt.alter_operation == AlterOperation.ADD_COLUMN
        assert stmt.column_name == "age"
        
    def test_identify_redundant_operations(self, temp_migrations_dir):
        """Test identification of redundant operations."""
        analyzer = MigrationAnalyzer()
        analysis = analyzer.analyze_directory(temp_migrations_dir)
        
        # Should detect redundant ALTER operations on age column
        assert len(analysis.redundant_operations) > 0
        
        # Check users table operations
        users_ops = analysis.table_operations['users']
        assert len(users_ops.redundant_alters) > 0
        
    def test_backup_pattern_detection(self, temp_migrations_dir):
        """Test detection of backup table patterns."""
        # Add a backup table migration
        (temp_migrations_dir / "005_backup_migration.sql").write_text("""
            CREATE TABLE users_backup AS SELECT * FROM users;
            DROP TABLE users;
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                age INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users (id, name, email, age) 
            SELECT id, name, email, age FROM users_backup;
            DROP TABLE users_backup;
        """)
        
        analyzer = MigrationAnalyzer()
        analysis = analyzer.analyze_directory(temp_migrations_dir)
        
        # Should detect backup pattern
        assert len(analysis.backup_patterns) > 0
        assert any('backup' in pattern.lower() for pattern in analysis.backup_patterns)
        
    def test_extract_sequence_number(self):
        """Test extraction of sequence numbers from filenames."""
        analyzer = MigrationAnalyzer()
        
        assert analyzer._extract_sequence_number("001_create_users.sql") == 1
        assert analyzer._extract_sequence_number("042_add_index.sql") == 42
        assert analyzer._extract_sequence_number("no_number.sql") == 999999
        
    def test_clean_sql(self):
        """Test SQL cleaning functionality."""
        analyzer = MigrationAnalyzer()
        
        sql_with_comments = """
        -- This is a comment
        CREATE TABLE test (
            id INTEGER PRIMARY KEY
            /* Multi-line
               comment */
        );
        """
        
        cleaned = analyzer._clean_sql(sql_with_comments)
        
        assert "--" not in cleaned
        assert "/*" not in cleaned
        assert "*/" not in cleaned
        assert "CREATE TABLE" in cleaned