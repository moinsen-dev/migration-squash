"""SQL dump-based baseline migration generator.

This module provides functionality to create a new baseline migration
by dumping the final state of a database after applying all existing migrations.
"""

import sqlite3
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
import re

from .analyzer import MigrationAnalyzer
from .models import MigrationFile


class DumpBaselineGenerator:
    """Generate baseline migration from SQL dump of the final database state."""

    def __init__(self):
        self.analyzer = MigrationAnalyzer()

    def generate_baseline(
        self,
        migrations_dir: Path,
        output_file: Optional[Path] = None,
        include_data: bool = False,
        clean_dump: bool = True
    ) -> Tuple[str, Path]:
        """
        Generate a baseline migration from existing migrations using SQL dump.

        Args:
            migrations_dir: Directory containing existing migrations
            output_file: Optional output file path for the baseline migration
            include_data: Whether to include INSERT statements for data
            clean_dump: Whether to clean and optimize the dump output

        Returns:
            Tuple of (dump_sql, output_path)
        """
        # Analyze existing migrations
        analysis = self.analyzer.analyze_directory(migrations_dir)

        # Create temporary database and apply all migrations
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = Path(tmp_db.name)

        try:
            # Apply all migrations to temporary database
            self._apply_migrations(db_path, analysis.migrations)

            # Generate SQL dump
            dump_sql = self._generate_dump(db_path, include_data)

            # Clean and optimize the dump if requested
            if clean_dump:
                dump_sql = self._clean_dump(dump_sql, include_data)

            # Add header and metadata
            dump_sql = self._add_metadata_header(dump_sql, analysis)

            # Determine output path
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = migrations_dir / f"baseline_{timestamp}.sql"

            # Write to file
            output_file.write_text(dump_sql, encoding='utf-8')

            return dump_sql, output_file

        finally:
            # Clean up temporary database
            if db_path.exists():
                db_path.unlink()

    def _apply_migrations(self, db_path: Path, migrations: List[MigrationFile]):
        """Apply all migrations to a database."""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        try:
            for migration in migrations:
                # Apply each migration file
                sql_content = migration.path.read_text(encoding='utf-8')

                # Execute all statements in the migration
                cursor.executescript(sql_content)
                conn.commit()

        finally:
            conn.close()

    def _generate_dump(self, db_path: Path, include_data: bool = False) -> str:
        """Generate SQL dump from database using sqlite3 command."""
        # Build sqlite3 command
        cmd = ['sqlite3', str(db_path)]

        # Add dump command with appropriate options
        if include_data:
            # Include both schema and data
            dump_cmd = '.dump'
        else:
            # Schema only - use .schema command
            dump_cmd = '.schema'

        # Execute sqlite3 with the dump command
        result = subprocess.run(
            cmd,
            input=dump_cmd,
            capture_output=True,
            text=True,
            check=True
        )

        return result.stdout

    def _clean_dump(self, dump_sql: str, include_data: bool) -> str:
        """Clean and optimize the SQL dump output."""
        lines = dump_sql.split('\n')
        cleaned_lines = []

        # Track whether we're in a transaction block
        in_transaction = False

        for line in lines:
            # Skip SQLite-specific pragma statements that aren't needed
            if line.startswith('PRAGMA foreign_keys'):
                continue

            # Skip BEGIN/COMMIT transaction blocks for schema-only dumps
            if not include_data:
                if line.strip() == 'BEGIN TRANSACTION;':
                    in_transaction = True
                    continue
                elif line.strip() == 'COMMIT;' and in_transaction:
                    in_transaction = False
                    continue

            # Clean up excessive whitespace
            line = re.sub(r'\s+', ' ', line).strip()

            # Skip empty lines
            if not line:
                continue

            # Format CREATE statements nicely
            if line.startswith('CREATE TABLE'):
                line = self._format_create_table(line)

            cleaned_lines.append(line)

        # Join with proper spacing
        result = []
        current_section = None

        for line in cleaned_lines:
            # Determine section type
            if line.startswith('CREATE TABLE'):
                new_section = 'table'
            elif line.startswith('CREATE INDEX'):
                new_section = 'index'
            elif line.startswith('CREATE TRIGGER'):
                new_section = 'trigger'
            elif line.startswith('CREATE VIEW'):
                new_section = 'view'
            elif line.startswith('CREATE VIRTUAL'):
                new_section = 'virtual'
            elif line.startswith('INSERT INTO') and include_data:
                new_section = 'data'
            else:
                new_section = current_section

            # Add spacing between sections
            if new_section != current_section and current_section is not None:
                result.append('')

            result.append(line)
            current_section = new_section

        return '\n'.join(result)

    def _format_create_table(self, create_stmt: str) -> str:
        """Format CREATE TABLE statements for better readability."""
        # This is a simple formatter - could be enhanced with sqlparse
        # For now, just ensure consistent spacing
        create_stmt = re.sub(r'\(\s+', '(', create_stmt)
        create_stmt = re.sub(r'\s+\)', ')', create_stmt)
        create_stmt = re.sub(r',\s+', ', ', create_stmt)

        return create_stmt

    def _add_metadata_header(self, dump_sql: str, analysis) -> str:
        """Add metadata header to the dump."""
        header = f"""-- =====================================================
-- Migration Baseline Generated by migration-squash
-- Generated: {datetime.now().isoformat()}
-- Original migrations: {len(analysis.migrations)} files
-- Original statements: {analysis.total_statements}
-- =====================================================

"""

        footer = """

-- =====================================================
-- End of baseline migration
-- =====================================================
"""

        return header + dump_sql + footer


class SmartDumpCleaner:
    """Advanced dump cleaning with intelligent pattern recognition."""

    def __init__(self):
        self.schema_elements = {
            'tables': [],
            'indexes': [],
            'triggers': [],
            'views': [],
            'virtual_tables': []
        }

    def clean_and_organize(self, dump_sql: str) -> str:
        """
        Clean and reorganize dump for optimal migration structure.

        Orders elements by dependency:
        1. Tables
        2. Indexes
        3. Views
        4. Virtual tables (FTS)
        5. Triggers
        """
        # Parse the dump into components
        self._parse_dump(dump_sql)

        # Reorganize by dependency order
        organized = []

        # Add tables first
        if self.schema_elements['tables']:
            organized.append("-- Tables")
            organized.extend(self.schema_elements['tables'])
            organized.append("")

        # Add indexes
        if self.schema_elements['indexes']:
            organized.append("-- Indexes")
            organized.extend(self.schema_elements['indexes'])
            organized.append("")

        # Add views
        if self.schema_elements['views']:
            organized.append("-- Views")
            organized.extend(self.schema_elements['views'])
            organized.append("")

        # Add virtual tables
        if self.schema_elements['virtual_tables']:
            organized.append("-- Virtual Tables (FTS)")
            organized.extend(self.schema_elements['virtual_tables'])
            organized.append("")

        # Add triggers last
        if self.schema_elements['triggers']:
            organized.append("-- Triggers")
            organized.extend(self.schema_elements['triggers'])
            organized.append("")

        return '\n'.join(organized)

    def _parse_dump(self, dump_sql: str):
        """Parse dump into categorized schema elements."""
        current_statement = []

        for line in dump_sql.split('\n'):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('--'):
                continue

            # Accumulate lines for multi-line statements
            current_statement.append(line)

            # Check if statement is complete (ends with semicolon)
            if line.endswith(';'):
                full_statement = ' '.join(current_statement)
                self._categorize_statement(full_statement)
                current_statement = []

    def _categorize_statement(self, statement: str):
        """Categorize a SQL statement into the appropriate schema element."""
        statement_upper = statement.upper()

        if statement_upper.startswith('CREATE VIRTUAL TABLE'):
            self.schema_elements['virtual_tables'].append(statement)
        elif statement_upper.startswith('CREATE TABLE'):
            self.schema_elements['tables'].append(statement)
        elif statement_upper.startswith('CREATE INDEX'):
            self.schema_elements['indexes'].append(statement)
        elif statement_upper.startswith('CREATE TRIGGER'):
            self.schema_elements['triggers'].append(statement)
        elif statement_upper.startswith('CREATE VIEW'):
            self.schema_elements['views'].append(statement)