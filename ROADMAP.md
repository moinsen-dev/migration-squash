# Migration Squash Tool - Multi-Database Support Roadmap

## 🎯 Vision

Transform the migration squash tool from SQLite-specific to a universal database migration optimization tool supporting SQLite, PostgreSQL, MySQL, and other major databases.

## 📊 Current State

- ✅ **SQLite**: Fully functional with advanced features
- ❌ **PostgreSQL**: Not supported
- ❌ **MySQL**: Not supported
- ❌ **Other DBs**: Not supported

## 🏗️ Architecture Roadmap

### Phase 1: Foundation - Database Abstraction Layer
**Timeline: 2-3 weeks**

#### 1.1 Create Database Adapter Pattern
```
src/
├── adapters/
│   ├── __init__.py
│   ├── base.py           # Abstract base adapter
│   ├── sqlite.py         # Current SQLite implementation
│   ├── postgresql.py     # New PostgreSQL adapter
│   └── mysql.py          # Future MySQL adapter
```

#### 1.2 Abstract Core Operations
- **Schema Introspection**: Table definitions, columns, constraints
- **Database Creation**: Test database setup for validation
- **SQL Generation**: Dialect-specific SQL output
- **Pattern Detection**: Database-specific migration patterns

#### 1.3 Refactor Existing Components
- Extract SQLite-specific code from `database_comparator.py`
- Move SQLite patterns to dedicated adapter
- Update CLI to accept database type parameter

### Phase 2: PostgreSQL Support
**Timeline: 3-4 weeks**

#### 2.1 PostgreSQL Adapter Implementation
```python
class PostgreSQLAdapter(DatabaseAdapter):
    def create_database(self, connection_string: str) -> str
    def extract_schema(self, db_path: str) -> Dict[str, Any]
    def get_table_info(self, conn, table_name: str) -> Dict[str, Any]
    def get_foreign_keys(self, conn, table_name: str) -> List[Dict]
    def execute_migration(self, conn, sql: str) -> None
```

#### 2.2 PostgreSQL-Specific Features
- **Data Type Mapping**: 
  ```python
  SQLITE_TO_POSTGRESQL = {
      'TEXT': 'VARCHAR',
      'INTEGER': 'INTEGER', 
      'REAL': 'DECIMAL',
      'BLOB': 'BYTEA'
  }
  ```

- **Schema Introspection**:
  ```sql
  -- PostgreSQL schema queries
  SELECT * FROM information_schema.tables 
  SELECT * FROM information_schema.columns
  SELECT * FROM information_schema.table_constraints
  ```

- **PostgreSQL Migration Patterns**:
  - Schema-qualified table names (`public.users`)
  - PostgreSQL-specific backup patterns
  - Extension handling (`CREATE EXTENSION`)

#### 2.3 Enhanced SQL Generation
- PostgreSQL-specific constraint syntax
- Handle PostgreSQL sequences and SERIAL types
- Support for PostgreSQL schemas and extensions

### Phase 3: Enhanced Validation & Testing
**Timeline: 2 weeks**

#### 3.1 Multi-Database Testing Framework
```
tests/
├── fixtures/
│   ├── sqlite/
│   │   ├── simple_migration/
│   │   └── complex_migration/
│   ├── postgresql/
│   │   ├── simple_migration/
│   │   └── complex_migration/
│   └── shared/
├── test_sqlite.py
├── test_postgresql.py
└── test_cross_database.py
```

#### 3.2 Database-Specific Test Scenarios
- **CREATE/DROP cycles** in each database
- **Complex constraints** (CHECK, FOREIGN KEY, UNIQUE)
- **Database-specific features** (virtual tables, extensions)
- **Large migration histories** (20+ files)

#### 3.3 Integration Testing
- Docker containers for database setup
- Automated testing in CI/CD pipeline
- Cross-database schema comparison

### Phase 4: Advanced Features
**Timeline: 3-4 weeks**

#### 4.1 Cross-Database Migration
```bash
# Convert SQLite migrations to PostgreSQL
uv run python -m src.cli convert \
  --source-db sqlite \
  --target-db postgresql \
  --input-dir ./sqlite_migrations \
  --output-dir ./postgresql_migrations
```

#### 4.2 Smart Data Type Conversion
- Intelligent type mapping with user overrides
- Handle database-specific constraints
- Preserve data integrity during conversion

#### 4.3 Advanced PostgreSQL Features
- **Partitioning**: Handle table partitions in squashing
- **Inheritance**: PostgreSQL table inheritance
- **Custom Types**: ENUM, composite types, domains
- **Extensions**: PostGIS, pg_crypto, etc.

### Phase 5: Additional Database Support
**Timeline: 4-6 weeks**

#### 5.1 MySQL/MariaDB Support
- MySQL-specific SQL dialect
- Handle MySQL storage engines (InnoDB, MyISAM)
- MySQL-specific constraints and indexes

#### 5.2 Cloud Database Support
- **Supabase**: PostgreSQL with Supabase-specific features
- **PlanetScale**: MySQL-compatible with unique constraints
- **Neon**: PostgreSQL with branching features

#### 5.3 NoSQL Database Exploration
- **MongoDB**: Schema evolution tracking
- **CouchDB**: Document-based migration patterns
- Initial research phase only

## 🔧 Implementation Details

### Configuration System
```python
# database_config.yaml
databases:
  sqlite:
    adapter: "sqlite"
    connection_template: "sqlite:///{path}"
    backup_patterns: ["*_backup", "*_temp", "*_old"]
  
  postgresql:
    adapter: "postgresql"
    connection_template: "postgresql://{user}:{pass}@{host}:{port}/{db}"
    backup_patterns: ["*_backup", "*_bak", "*_archive"]
    
  mysql:
    adapter: "mysql"
    connection_template: "mysql://{user}:{pass}@{host}:{port}/{db}"
    backup_patterns: ["*_backup", "*_old"]
```

### CLI Interface Evolution
```bash
# Current (SQLite-only)
uv run python -m src.cli squash ./migrations --output-dir ./output

# Future (Multi-database)
uv run python -m src.cli squash ./migrations \
  --database postgresql \
  --connection-string "postgresql://user:pass@localhost/db" \
  --output-dir ./output

# Cross-database conversion
uv run python -m src.cli convert \
  --from sqlite --to postgresql \
  --input ./sqlite_migrations \
  --output ./postgresql_migrations
```

### Error Handling & Validation
- Database-specific error messages
- Connection validation before processing
- Rollback capabilities for failed operations
- Detailed logging for debugging

## 📈 Success Metrics

### Phase 1 Success Criteria
- [ ] Clean separation of SQLite-specific code
- [ ] Abstract base adapter with clear interface  
- [ ] All existing SQLite functionality preserved
- [ ] 100% backward compatibility

### Phase 2 Success Criteria
- [ ] PostgreSQL adapter fully functional
- [ ] Complex PostgreSQL migrations squashed correctly
- [ ] Database validation passes for PostgreSQL
- [ ] Performance comparable to SQLite version

### Phase 3 Success Criteria
- [ ] Comprehensive test coverage (>90%)
- [ ] Both SQLite and PostgreSQL tests pass
- [ ] CI/CD pipeline validates both databases
- [ ] Documentation covers all supported databases

### Phases 4-5 Success Criteria
- [ ] Cross-database conversion working
- [ ] MySQL support functional
- [ ] Cloud database integrations tested
- [ ] Performance benchmarks meet targets

## 🚀 Getting Started

### Immediate Next Steps
1. **Create adapter interfaces** in `src/adapters/base.py`
2. **Refactor SQLite code** to use adapter pattern
3. **Design configuration system** for database selection
4. **Set up testing framework** with Docker containers

### Development Priorities
1. **Backward Compatibility**: Never break existing SQLite functionality  
2. **Performance**: Multi-database support shouldn't slow down operations
3. **Maintainability**: Clean architecture that's easy to extend
4. **Documentation**: Comprehensive guides for each database

## 🤝 Community & Contributions

### Contribution Areas
- **Database Adapters**: Implement support for new databases
- **Testing**: Create comprehensive test scenarios  
- **Documentation**: Database-specific guides and examples
- **Performance**: Optimize for large migration histories

### Integration Opportunities
- **ORMs**: Integrate with Django, SQLAlchemy, Prisma migrations
- **CI/CD**: GitHub Actions, GitLab CI integration
- **Cloud Platforms**: Heroku, Vercel, Railway deployment guides
- **Database Tools**: Integration with database management tools

## 📚 Resources & References

### Technical Resources
- [PostgreSQL Information Schema](https://www.postgresql.org/docs/current/information-schema.html)
- [MySQL Information Schema](https://dev.mysql.com/doc/refman/8.0/en/information-schema.html)
- [SQLAlchemy Dialects](https://docs.sqlalchemy.org/en/14/dialects/) - Reference for SQL dialect differences
- [Django Database Backends](https://docs.djangoproject.com/en/4.2/ref/databases/) - Multi-database patterns

### Database-Specific Migration Tools
- **PostgreSQL**: `pg_dump`, `pg_migrate`  
- **MySQL**: `mysqldump`, `migrate`
- **SQLite**: Current implementation reference

---

## 📝 Notes

This roadmap is designed to be **evolutionary**, not revolutionary. Each phase builds on the previous one while maintaining full backward compatibility. The goal is to create a robust, extensible tool that becomes the go-to solution for database migration optimization across the ecosystem.

**Last Updated**: January 2025  
**Status**: Planning Phase  
**Next Review**: After Phase 1 completion