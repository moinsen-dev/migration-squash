# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-01-16

### Added
- **New `dump-baseline` command** - Generate baseline migrations from SQL dump
  - Creates a single consolidated migration from existing migration history
  - Uses SQLite's native dump functionality for accurate schema extraction
  - Perfect for projects with 15-50+ migrations that need consolidation
  - Supports schema-only or schema+data dumps
  - Intelligent dump cleaning and optimization
  - Automatic organization by dependency order (tables → indexes → views → virtual tables → triggers)

### Features
- Generate baseline migrations using `migration-squash dump-baseline`
- Option to include or exclude data (INSERT statements)
- Smart dump cleaning to remove unnecessary SQLite pragmas
- Organize schema elements by dependency order for better readability
- Automatic timestamped filenames or custom output paths
- Full support for complex SQLite features (FTS, triggers, views)
- Comprehensive test coverage for baseline generation

### Improvements
- Updated CLI version to 0.2.0
- Enhanced documentation with dump-baseline examples

## [0.1.0] - 2025-01-15

### Added
- Initial release as standalone tool
- Extracted from MCP-Hive project as independent package
- Full feature parity with original implementation
- PyPI package support with proper entry points
- MIT license for open source distribution