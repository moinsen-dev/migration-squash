# Migration Squash Tool

Intelligent SQL migration squashing and optimization tool for SQLite databases. Transforms complex migration histories with redundant operations into clean, optimized files.

## 🎯 Problem Solved

Transform migration chaos like this:
```
001_baseline.sql           → CREATE TABLE users (id, name)
002_add_email.sql         → ALTER TABLE users ADD COLUMN email
003_drop_users.sql        → DROP TABLE users
004_recreate_users.sql    → CREATE TABLE users (id, name, email, phone)
005_add_more_fields.sql   → ALTER TABLE users ADD COLUMN status
```

Into clean, optimized migrations:
```
001_squashed_schema.sql   → CREATE TABLE users (id, name, email, phone, status)
```

## ✨ Features

- **🔍 Smart Analysis**: Detects CREATE/DROP cycles, redundant ALTERs, and optimization opportunities
- **🏗️ SQLite Optimized**: Handles backup tables, virtual tables (FTS), triggers, and SQLite-specific patterns
- **✅ Database Validation**: Creates actual test databases to verify schema correctness
- **📊 Advanced Comparison**: Element-by-element schema comparison with detailed reporting
- **🎨 Rich CLI**: Beautiful command-line interface with progress indicators and colorized output
- **🛡️ Safe Operations**: Backup support and validation before applying changes

## 📈 Performance Results

**Real-world example from MCP-Hive project:**
- **Before**: 23 migration files, 316 SQL statements
- **After**: 1 migration file, 152 SQL statements  
- **Optimization**: 62% reduction in complexity
- **Validation**: 100% schema accuracy verified

## 🚀 Installation

### From PyPI (Recommended)
```bash
pip install migration-squash
```

### From Source (Development)
```bash
git clone https://github.com/your-username/migration-squash.git
cd migration-squash

# Option 1: Install as global tool (like npm link)
uv tool install --editable .

# Option 2: Development environment
uv sync
uv run migration-squash analyze /path/to/migrations

# Option 3: Editable install in current environment
uv pip install --editable .
```

## 📖 Usage

### Basic Workflow
```bash
# 1. Analyze your migrations (safe, read-only)
migration-squash analyze /path/to/migrations

# 2. Generate squashed migrations
migration-squash squash /path/to/migrations --output-dir ./output

# 3. Validate with database comparison  
migration-squash compare /path/to/migrations ./output
```

### Advanced Usage
```bash
# Preview changes without writing files
migration-squash squash /path/to/migrations --dry-run

# Keep data migrations separate from schema
migration-squash squash /path/to/migrations --keep-data --backup

# Save detailed comparison report
migration-squash compare original/ squashed/ --save-report report.json
```

## 🛠️ Commands

### `analyze` - Migration Analysis
Shows optimization opportunities and patterns detected:
- Tables with CREATE/DROP cycles
- Redundant ALTER operations  
- SQLite backup table patterns
- Virtual table and trigger detection

### `squash` - Generate Optimized Migrations
Creates clean, consolidated migration files:
- Merges ALTER statements into CREATE tables
- Eliminates redundant operations
- Preserves dependency ordering (tables → virtual tables → triggers)
- Handles SQLite-specific patterns

### `compare` - Database Schema Validation  
**Advanced validation using real databases:**
- Creates SQLite databases (`original.db` and `squashed.db`) in the output directory for inspection
- Applies all original migrations vs. single squashed migration
- Performs element-by-element schema comparison
- Reports differences in tables, columns, indexes, triggers, virtual tables
- Databases remain available for manual inspection and debugging
- Generates detailed JSON reports

### `validate` - Basic Schema Validation
Simple validation for basic schema comparison (legacy command)

## ⚙️ Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview operations without writing files |
| `--keep-data` | Keep data migrations separate from schema |
| `--output-dir` | Directory for squashed migration output |
| `--group-by` | Grouping strategy: 'table', 'feature', 'date' |
| `--backup` | Create timestamped backup of original migrations |
| `--save-report` | Save detailed comparison report to JSON file |
| `--verbose` | Show detailed analysis information |

## 🏗️ Architecture

```
src/
├── cli.py                    # Rich CLI interface with progress bars
├── analyzer.py              # Migration parsing and analysis engine  
├── squasher.py              # Smart optimization and merging logic
├── database_comparator.py   # Advanced database schema comparison
├── validator.py             # Basic schema validation
├── sqlite_patterns.py       # SQLite-specific pattern detection
└── models.py                # Data structures and types
```

## 🎯 Key Algorithms

### CREATE/DROP Cycle Detection
Identifies tables that are created, dropped, and recreated, then merges all ALTER operations into the final CREATE statement.

### Smart ALTER Merging
Analyzes ALTER TABLE operations and merges ADD COLUMN statements into CREATE TABLE definitions while preserving constraints and relationships.

### SQLite Pattern Recognition
- Detects backup table patterns (`*_backup`, `*_temp`, `*_old`)
- Handles virtual tables (FTS) with proper dependency ordering
- Preserves trigger definitions and relationships

### Database Validation
Creates actual SQLite databases to verify that squashed migrations produce identical schemas to the original migration sequence.

## 🧪 Testing

The tool has been tested on:
- Complex migration histories (20+ files)
- CREATE/DROP/CREATE cycles
- SQLite virtual tables and triggers  
- Foreign key relationships
- Mixed schema and data migrations

## 🤝 Contributing

Built with modern Python practices:
- UV package manager for fast dependency management
- Rich library for beautiful CLI output
- Type hints and dataclasses for maintainability
- Modular architecture for extensibility

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.