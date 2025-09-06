"""Command-line interface for migration squashing tool."""

import sys
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm

from .analyzer import MigrationAnalyzer
from .squasher import MigrationSquasher, SquashConfig
from .sqlite_patterns import SQLitePatternDetector, SQLiteOptimizer
from .validator import MigrationValidator
from .database_comparator import DatabaseComparator


console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Intelligent SQL migration squashing tool for SQLite databases.
    
    This tool analyzes migration files to detect redundant operations
    and generates optimized, squashed migration files.
    """
    pass


@cli.command()
@click.argument('migrations_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--verbose', '-v', is_flag=True, help='Show detailed analysis')
def analyze(migrations_dir: Path, verbose: bool):
    """Analyze migration files and show optimization opportunities."""
    console.print(f"🔍 Analyzing migrations in: [bold blue]{migrations_dir}[/bold blue]")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing migrations...", total=None)
            
            analyzer = MigrationAnalyzer()
            analysis = analyzer.analyze_directory(migrations_dir)
            
            progress.update(task, description="Detecting SQLite patterns...")
            pattern_detector = SQLitePatternDetector()
            backup_patterns = pattern_detector.detect_backup_table_migrations(analysis.migrations)
        
        # Display results
        _display_analysis_results(analysis, backup_patterns, verbose)
        
    except Exception as e:
        console.print(f"❌ Error analyzing migrations: [red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('migrations_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--output-dir', '-o', type=click.Path(path_type=Path), 
              help='Output directory for squashed migrations')
@click.option('--dry-run', is_flag=True, help='Preview operations without writing files')
@click.option('--group-by', type=click.Choice(['table', 'feature', 'date']), 
              default='table', help='Grouping strategy')
@click.option('--keep-data', is_flag=True, 
              help='Keep data migrations separate from schema')
@click.option('--backup', is_flag=True, 
              help='Create backup of original migrations')
def squash(migrations_dir: Path, output_dir: Optional[Path], dry_run: bool, 
          group_by: str, keep_data: bool, backup: bool):
    """Generate optimized, squashed migration files."""
    if not output_dir:
        output_dir = migrations_dir.parent / "squashed_migrations"
    
    console.print(f"🔧 Squashing migrations from: [bold blue]{migrations_dir}[/bold blue]")
    console.print(f"📁 Output directory: [bold green]{output_dir}[/bold green]")
    
    if dry_run:
        console.print("🔍 [yellow]DRY RUN MODE - No files will be written[/yellow]")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            # Analyze
            task1 = progress.add_task("Analyzing migrations...", total=100)
            analyzer = MigrationAnalyzer()
            analysis = analyzer.analyze_directory(migrations_dir)
            progress.update(task1, completed=50)
            
            # Configure squashing
            config = SquashConfig(
                group_by=group_by,
                keep_data_separate=keep_data
            )
            
            # Squash
            progress.update(task1, description="Squashing migrations...", completed=75)
            squasher = MigrationSquasher(config)
            result = squasher.squash(analysis)
            progress.update(task1, completed=100)
        
        # Display results
        _display_squash_results(result, dry_run)
        
        if not dry_run:
            # Create backup if requested
            if backup:
                _create_backup(migrations_dir, console)
            
            # Write output files
            if not output_dir.exists():
                output_dir.mkdir(parents=True)
            
            _write_squashed_files(result, output_dir)
            console.print(f"✅ Squashed migrations written to: [bold green]{output_dir}[/bold green]")
        
    except Exception as e:
        console.print(f"❌ Error squashing migrations: [red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('original_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument('squashed_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--db-url', help='Database URL for validation (optional)')
def validate(original_dir: Path, squashed_dir: Path, db_url: Optional[str]):
    """Validate that squashed migrations produce the same schema."""
    console.print("🔍 Validating squashed migrations...")
    
    try:
        validator = MigrationValidator()
        is_valid = validator.validate_squashed_migrations(original_dir, squashed_dir, db_url)
        
        if is_valid:
            console.print("✅ [green]Validation passed![/green] Squashed migrations produce identical schema.")
        else:
            console.print("❌ [red]Validation failed![/red] Schema differences detected.")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"❌ Error validating migrations: [red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument('original_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument('squashed_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--save-report', type=click.Path(path_type=Path), help='Save detailed report to JSON file')
def compare(original_dir: Path, squashed_dir: Path, save_report: Optional[Path]):
    """Advanced database comparison between original and squashed migrations.
    
    Creates actual databases from both migration sets and compares the complete
    schema including tables, columns, indexes, triggers, and virtual tables.
    """
    console.print("🔍 [bold]Advanced Database Schema Comparison[/bold]")
    console.print(f"📁 Original migrations: [blue]{original_dir}[/blue]")
    console.print(f"📁 Squashed migrations: [blue]{squashed_dir}[/blue]")
    console.print()
    
    try:
        comparator = DatabaseComparator()
        result = comparator.compare_migrations(original_dir, squashed_dir, squashed_dir)
        
        # Display results
        comparator.display_comparison_results(result)
        
        # Save detailed report if requested
        if save_report:
            report_data = {
                'identical': result.identical,
                'differences': result.differences,
                'missing_in_squashed': result.missing_in_squashed,
                'extra_in_squashed': result.extra_in_squashed,
                'modified_elements': result.modified_elements,
                'summary': {
                    'total_differences': len(result.differences),
                    'missing_elements': len(result.missing_in_squashed),
                    'extra_elements': len(result.extra_in_squashed),
                    'modified_elements': len(result.modified_elements)
                }
            }
            
            import json
            save_report.write_text(json.dumps(report_data, indent=2), encoding='utf-8')
            console.print(f"📄 Detailed report saved to: [green]{save_report}[/green]")
        
        # Exit with appropriate code
        if result.identical:
            console.print("\n🎉 [green]Database schemas are identical![/green]")
        else:
            console.print(f"\n❌ [red]Found {len(result.differences)} schema differences.[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"❌ Error comparing databases: [red]{e}[/red]")
        sys.exit(1)


def _display_analysis_results(analysis, backup_patterns, verbose: bool):
    """Display analysis results in a formatted way."""
    # Summary panel
    summary_text = Text()
    summary_text.append(f"Migration files: {len(analysis.migrations)}\\n")
    summary_text.append(f"Total statements: {analysis.total_statements}\\n")
    summary_text.append(f"Tables affected: {len(analysis.table_operations)}\\n")
    summary_text.append(f"Optimization potential: {analysis.optimization_potential} statements")
    
    console.print(Panel(summary_text, title="📊 Analysis Summary", border_style="blue"))
    
    # Tables with issues
    if analysis.tables_with_issues:
        table = Table(title="⚠️ Tables with Optimization Opportunities")
        table.add_column("Table Name", style="cyan")
        table.add_column("Issues", style="yellow")
        table.add_column("Redundant Operations", justify="right", style="red")
        
        for table_name in analysis.tables_with_issues:
            ops = analysis.table_operations[table_name]
            issues = []
            if ops.has_create_drop_cycle:
                issues.append("CREATE/DROP cycle")
            if ops.redundant_alters:
                issues.append("Redundant ALTERs")
            
            table.add_row(
                table_name,
                ", ".join(issues),
                str(len(ops.redundant_alters))
            )
        
        console.print(table)
    
    # Backup patterns
    if backup_patterns:
        console.print(f"\\n🔄 Found {len(backup_patterns)} backup table patterns")
        if verbose:
            for pattern in backup_patterns:
                console.print(f"  • {pattern.migration_file}: {pattern.original_table} -> {pattern.backup_table}")
    
    # Recommendations
    recommendations = []
    if analysis.optimization_potential > 10:
        recommendations.append("High optimization potential - squashing recommended")
    if backup_patterns:
        recommendations.append("SQLite backup patterns detected - can be optimized")
    if analysis.tables_with_issues:
        recommendations.append(f"{len(analysis.tables_with_issues)} tables have redundant operations")
    
    if recommendations:
        rec_text = "\\n".join(f"• {rec}" for rec in recommendations)
        console.print(Panel(rec_text, title="💡 Recommendations", border_style="green"))


def _display_squash_results(result, dry_run: bool):
    """Display squashing results."""
    # Results panel
    results_text = Text()
    results_text.append(f"Original files: {result.original_files}\\n")
    results_text.append(f"Squashed files: {result.squashed_files}\\n")
    results_text.append(f"Statements reduced: {result.statements_reduced}\\n")
    
    if result.data_sql:
        results_text.append("Schema and data migrations separated\\n")
    
    optimization_pct = (result.statements_reduced / (result.statements_reduced + 100)) * 100
    results_text.append(f"Optimization: ~{optimization_pct:.1f}% reduction")
    
    title = "🎯 Squashing Results (Preview)" if dry_run else "🎯 Squashing Results"
    console.print(Panel(results_text, title=title, border_style="green"))


def _create_backup(migrations_dir: Path, console: Console):
    """Create backup of original migrations."""
    import shutil
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = migrations_dir.parent / f"migrations_backup_{timestamp}"
    
    shutil.copytree(migrations_dir, backup_dir)
    console.print(f"💾 Backup created: [dim]{backup_dir}[/dim]")


def _write_squashed_files(result, output_dir: Path):
    """Write squashed migration files to output directory."""
    # Write schema migration
    schema_file = output_dir / "001_squashed_schema.sql"
    schema_file.write_text(result.schema_sql, encoding='utf-8')
    
    # Write data migration if exists
    if result.data_sql:
        data_file = output_dir / "002_squashed_data.sql"
        data_file.write_text(result.data_sql, encoding='utf-8')
    
    # Write metadata
    import json
    metadata_file = output_dir / "squash_metadata.json"
    metadata_file.write_text(json.dumps(result.metadata, indent=2), encoding='utf-8')


def main():
    """Main CLI entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Unexpected error: [red]{e}[/red]")
        sys.exit(1)


if __name__ == '__main__':
    main()