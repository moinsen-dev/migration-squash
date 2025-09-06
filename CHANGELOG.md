# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial standalone release of migration-squash tool
- Smart SQL migration analysis and optimization
- SQLite-specific pattern detection and handling
- Advanced database schema validation and comparison
- Rich CLI interface with progress indicators
- Comprehensive test suite and validation

### Features
- **analyze** command for migration analysis and optimization detection
- **squash** command for generating clean, consolidated migrations
- **compare** command for advanced database schema validation
- **validate** command for basic schema comparison
- Support for CREATE/DROP cycle detection and optimization
- Smart ALTER statement merging into CREATE statements
- SQLite backup table pattern handling
- Virtual table (FTS) and trigger preservation
- Dependency ordering preservation
- Dry-run mode for safe preview of changes
- Backup creation for original migrations
- JSON report generation for detailed analysis

## [0.1.0] - 2025-01-15

### Added
- Initial release as standalone tool
- Extracted from MCP-Hive project as independent package
- Full feature parity with original implementation
- PyPI package support with proper entry points
- MIT license for open source distribution