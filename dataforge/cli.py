import json
from collections import defaultdict

import click
from .core.scanner import scan_directory
from .modules.duplicates import build_duplicate_export_rows, build_duplicate_records, find_duplicates, order_duplicate_records, serialize_duplicate_record
from .modules.search import SearchQuery, build_search_query, export_result_rows, iter_search_files, order_search_results, search_files
from .modules.organizer import Organizer
from .modules.renamer import bulk_rename
from .modules.cleaner import remove_empty_folders
from .modules.usage import analyze_size, generate_usage_report
from .modules.integrity import IntegrityMonitor


def _serialize_search_result(entry):
    return {
        'path': entry.path,
        'filename': entry.filename,
        'extension': entry.extension,
        'size': entry.size,
        'created_at': entry.created_at,
        'modified_at': entry.modified_at,
        'is_dir': entry.is_dir,
    }


def _raise_search_usage_error(message, error_format):
    if error_format == 'json':
        click.echo(json.dumps({
            'ok': False,
            'error': {
                'type': 'usage',
                'command': 'search',
                'message': message,
                'exit_code': 2,
            },
        }), err=True)
        raise click.exceptions.Exit(2)

    raise click.UsageError(message)


def _write_duplicate_text_report(records, output_path):
    grouped = defaultdict(list)
    for record in records:
        grouped[record['hash']].append(record)

    with open(output_path, 'w', encoding='utf-8') as handle:
        for hash_value in sorted(grouped):
            group_records = grouped[hash_value]
            handle.write(f"Hash: {hash_value} (Group Size: {group_records[0]['group_size']})\n")
            for record in group_records:
                handle.write(f"  - {record['entry'].path}\n")
            handle.write("\n")

@click.group()
def main():
    """DataForge CLI — file & system intelligence toolkit"""
    pass

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True)
def scan(path, recursive):
    """List files in a directory."""
    for entry in scan_directory(path, recursive):
        click.echo(f"{entry.path} ({entry.size} bytes)")

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--max-depth', type=int, default=-1, show_default=True, help='Maximum directory depth to scan (-1 means unlimited)')
@click.option('--sort', 'sort_key', type=click.Choice(['group', 'ext', 'path', 'name', 'size', 'created', 'modified']), help='Sort duplicate rows before output/export')
@click.option('--reverse', is_flag=True, help='Reverse the chosen duplicate output order')
@click.option('--limit', type=click.IntRange(min=1), help='Maximum number of duplicate rows to keep in the visible/exported slice')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'jsonl']), default='text', show_default=True, help='Stdout output format')
@click.option('--output', '-o', type=click.Path(), help='Optional file path for exporting the current duplicate slice')
@click.option('--export-format', type=click.Choice(['csv', 'json', 'txt']), help='Export format for --output (defaults from the file extension)')
@click.option('--flat-export', is_flag=True, help='Exclude duplicate group summary rows from CSV/JSON exports')
@click.option('--count-only', is_flag=True, help='Print only the number of duplicate rows in the current slice; overrides --format')
def dupes(path, max_depth, sort_key, reverse, limit, output_format, output, export_format, flat_export, count_only):
    """Find duplicate files.

    Examples:
      fm dupes PATH --sort group --reverse --limit 20
      fm dupes PATH --count-only
      fm dupes PATH --format jsonl
            fm dupes PATH --output duplicates.json --flat-export
      fm dupes PATH --sort size --output duplicates.csv --export-format csv
    """
    duplicates = find_duplicates(path, max_depth=max_depth)
    total_rows = sum(len(v) for v in duplicates.values())
    records = order_duplicate_records(build_duplicate_records(duplicates), sort_key=sort_key, reverse=reverse, limit=limit)

    if count_only:
        click.echo(str(len(records)))
        return

    click.echo(f"Scanning for duplicates in {path}...")
    click.echo(f"Found {len(duplicates)} sets of duplicates ({total_rows} files total, {len(records)} in current slice).")

    if output_format == 'json':
        click.echo(json.dumps([serialize_duplicate_record(record) for record in records], indent=2))
    else:
        for record in records:
            if output_format == 'jsonl':
                click.echo(json.dumps(serialize_duplicate_record(record)))
            else:
                click.echo(f"{record['hash']}\t{record['entry'].path}")

    if not output:
        return

    chosen_export_format = export_format
    if not chosen_export_format:
        chosen_export_format = 'json' if str(output).lower().endswith('.json') else 'txt' if str(output).lower().endswith('.txt') else 'csv'

    if chosen_export_format == 'txt':
        _write_duplicate_text_report(records, output)
    else:
        export_result_rows(build_duplicate_export_rows(records, include_group_summary=not flat_export), output, format=chosen_export_format)

    click.echo(f"Report saved to {output}")

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--name-glob', help='Glob pattern for filename (for example *.txt)')
@click.option('--name-regex', help='Regex pattern for filename')
@click.option('--ext', help='Comma separated extensions (e.g. jpg,png)')
@click.option('--content', help='Literal text to search inside file contents')
@click.option('--content-regex', is_flag=True, help='Treat --content as a regular expression')
@click.option('--case-sensitive', is_flag=True, help='Make content search case-sensitive')
@click.option('--min-size', type=int, help='Min size in bytes')
@click.option('--max-size', type=int, help='Max size in bytes')
@click.option('--newer-than-days', type=float, help='Only include files modified within the last N days')
@click.option('--older-than-days', type=float, help='Only include files modified more than N days ago')
@click.option('--max-depth', type=int, default=-1, show_default=True, help='Maximum directory depth to scan (-1 means unlimited)')
@click.option('--sort', 'sort_key', type=click.Choice(['ext', 'path', 'name', 'size', 'created', 'modified']), help='Sort matches before output')
@click.option('--reverse', is_flag=True, help='Reverse the chosen output order')
@click.option('--limit', type=click.IntRange(min=1), help='Maximum number of matches to output')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'jsonl']), default='text', show_default=True, help='Result output format')
@click.option('--error-format', type=click.Choice(['text', 'json']), default='text', show_default=True, help='Format invalid CLI-combination errors for scripting')
@click.option('--count-only', is_flag=True, help='Print only the number of matches; overrides --format')
def search(path, name_glob, name_regex, ext, content, content_regex, case_sensitive, min_size, max_size, newer_than_days, older_than_days, max_depth, sort_key, reverse, limit, output_format, error_format, count_only):
    """Search for files.

        Note: --count-only ignores --format and prints only the integer match count.

    \b
    Examples:
      fm search PATH --sort ext
      fm search PATH --sort ext --reverse
            fm search PATH --count-only
            fm search PATH --sort size --reverse --limit 20
    """
    if name_glob and name_regex:
        _raise_search_usage_error('Use either --name-glob or --name-regex, not both.', error_format)

    query = build_search_query(
        name_pattern=name_regex or name_glob,
        use_regex=bool(name_regex),
        extensions=ext,
        content_text=content,
        content_is_regex=content_regex,
        case_sensitive=case_sensitive,
        min_size_bytes=min_size,
        max_size_bytes=max_size,
        newer_than_days=newer_than_days,
        older_than_days=older_than_days,
    )

    if count_only:
        if sort_key or reverse:
            results = list(iter_search_files(path, query, max_depth=max_depth))
            results = order_search_results(results, sort_key=sort_key, reverse=reverse, limit=limit)
            match_count = len(results)
        elif limit is not None:
            match_count = 0
            for _ in iter_search_files(path, query, max_depth=max_depth):
                match_count += 1
                if match_count >= limit:
                    break
        else:
            match_count = sum(1 for _ in iter_search_files(path, query, max_depth=max_depth))
        click.echo(str(match_count))
        return

    if output_format == 'json' or sort_key or reverse:
        results = search_files(path, query, max_depth=max_depth)
        results = order_search_results(results, sort_key=sort_key, reverse=reverse, limit=limit)

    if output_format == 'json':
        click.echo(json.dumps([_serialize_search_result(res) for res in results], indent=2))
        return

    emitted = 0
    result_iterable = results if (sort_key or reverse) else iter_search_files(path, query, max_depth=max_depth)
    for res in result_iterable:
        if output_format == 'jsonl':
            click.echo(json.dumps(_serialize_search_result(res)))
        else:
            click.echo(f"{res.path}")

        emitted += 1
        if limit is not None and emitted >= limit:
            break

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--dest', required=True, type=click.Path())
@click.option('--action', type=click.Choice(['move', 'copy']), default='copy')
@click.option('--name', help='Filter by name regex')
@click.option('--ext', help='Filter by extension')
@click.option('--dry-run/--execute', default=True, help='Preview without moving')
def organize(path, dest, action, name, ext, dry_run):
    """Organize files matching criteria."""
    query = build_search_query(
        name_pattern=name,
        use_regex=bool(name),
        extensions=ext,
    )
        
    log = Organizer.organize_files(path, query, action, dest, dry_run)
    for line in log:
        click.echo(line)

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--pattern', required=True, help='Regex pattern to match')
@click.option('--repl', required=True, help='Replacement string')
@click.option('--dry-run/--execute', default=True)
def rename(path, pattern, repl, dry_run):
    """Bulk rename files."""
    log = bulk_rename(path, pattern, repl, recursive=False, dry_run=dry_run)
    for line in log:
        click.echo(line)

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--dry-run/--execute', default=True)
def clean(path, dry_run):
    """Remove empty folders."""
    log = remove_empty_folders(path, dry_run)
    for line in log:
        click.echo(line)

@main.command()
@click.argument('path', type=click.Path(exists=True))
def usage(path):
    """Analyze disk usage."""
    data = analyze_size(path)
    report = generate_usage_report(data)
    for line in report:
        click.echo(line)

@click.group()
def integrity():
    """File integrity tools."""
    pass

main.add_command(integrity)

@integrity.command()
@click.argument('path', type=click.Path(exists=True))
@click.argument('snapshot', type=click.Path())
def create(path, snapshot):
    """Create a snapshot of file hashes."""
    report = IntegrityMonitor.create_snapshot(path, snapshot)
    click.echo(f"Snapshot created at {snapshot}")
    click.echo(f"Scanned: {report['scanned']}  Saved: {report['saved']}  Skipped: {report['skipped']}")

@integrity.command()
@click.argument('path', type=click.Path(exists=True))
@click.argument('snapshot', type=click.Path(exists=True))
def check(path, snapshot):
    """Verify files against a snapshot."""
    report = IntegrityMonitor.verify_snapshot(path, snapshot)
    issues = report["discrepancies"]
    if not issues:
        click.echo("Integrity check passed: No changes detected.")
    else:
        for issue in issues:
            click.echo(issue)

@main.command()
@click.option('--path', type=click.Path(exists=True), help='Additional path to scan')
@click.option('--category', '-c', multiple=True, help='Categories to scan (default: all)')
@click.option('--min-age', type=int, default=0, help='Only include files older than N days')
@click.option('--dry-run/--execute', default=True, help='Preview cleanup without deleting')
def cleanup(path, category, min_age, dry_run):
    """Scan and remove junk files."""
    import os
    from .modules.system_cleanup import scan_junk_files, estimate_cleanup_savings
    from .core.services import FileActionService
    from .core.utils import format_size
    
    categories = list(category) if category else None
    paths = [path] if path else None
    
    click.echo("Scanning for junk files...")
    results = scan_junk_files(paths=paths, categories=categories, min_age_days=min_age)
    savings = estimate_cleanup_savings(results)
    
    click.echo(f"Found {savings['total_files']} junk files ({savings['formatted_total']} reclaimable).")
    
    for cat, entries in results.items():
        click.echo(f"\nCategory: {cat} ({len(entries)} files)")
        for entry in entries[:10]:
            click.echo(f"  - {entry.path} ({format_size(entry.size)})")
        if len(entries) > 10:
            click.echo(f"  ... and {len(entries) - 10} more")
            
    if not results:
        return
        
    if dry_run:
        click.echo("\nDry-run mode. Run with --execute to perform actual deletion.")
    else:
        if click.confirm("\nAre you sure you want to delete these files?"):
            targets = [{"source_path": entry.path} for entries in results.values() for entry in entries]
            outcome = FileActionService.delete_items(
                targets,
                dry_run=False,
                path_getter=lambda t: t["source_path"]
            )
            click.echo(f"Cleanup complete. Deleted: {len(outcome.successes)} | Failed: {len(outcome.failures)}")

@main.command()
@click.option('--processes', is_flag=True, help='List top resource-heavy processes')
@click.option('--startup', is_flag=True, help='List system startup items')
@click.option('--disk-health', is_flag=True, help='Check disk S.M.A.R.T. health status')
def performance(processes, startup, disk_health):
    """View system performance metrics and diagnostics."""
    from .modules.performance import get_system_info, get_running_processes, get_startup_items, get_disk_health
    from .core.utils import format_size
    
    if processes:
        procs = get_running_processes(sort_by="memory", limit=15)
        click.echo("Top Processes by Memory:")
        click.echo(f"{'PID':<8}{'Name':<25}{'CPU %':<8}{'MEM %':<8}{'Size':<10}")
        for p in procs:
            click.echo(f"{p['pid']:<8}{p['name'][:24]:<25}{p['cpu_percent']:<8.1f}{p['memory_percent']:<8.1f}{format_size(p.get('memory_bytes', 0)):<10}")
    elif startup:
        items = get_startup_items()
        click.echo("Startup Items:")
        click.echo(f"{'Name':<25}{'Type':<12}{'Scope':<10}{'Enabled':<8}")
        for item in items:
            click.echo(f"{item.get('name', '—')[:24]:<25}{item.get('type', '—'):<12}{item.get('scope', '—'):<10}{'Yes' if item.get('enabled') else 'No':<8}")
    elif disk_health:
        health = get_disk_health()
        if "error" in health:
            click.echo(f"Error checking disk health: {health['error']}")
        else:
            click.echo("Disk S.M.A.R.T. Health Status:")
            click.echo(f"{'Device':<15}{'Status':<12}{'Temp (°C)':<10}{'Details':<20}")
            for device, info in health.items():
                status = "PASSED" if info.get("healthy") else "FAILED" if "healthy" in info else "Unknown"
                temp = str(info.get("temperature_c", "—"))
                click.echo(f"{device:<15}{status:<12}{temp:<10}{info.get('error', 'OK'):<20}")
    else:
        info = get_system_info()
        sys_info = info.get("system", {})
        cpu_info = info.get("cpu", {})
        ram_info = info.get("ram", {})
        click.echo("System Overview:")
        click.echo(f"  OS: {sys_info.get('os', '')} {sys_info.get('os_release', '')} ({sys_info.get('distro', '—')})")
        click.echo(f"  CPU: {cpu_info.get('model', '—')} ({cpu_info.get('physical_cores', '?')} cores)")
        click.echo(f"  RAM: {ram_info.get('formatted_total', '—')}")
        click.echo(f"  Uptime: {info.get('uptime', {}).get('uptime_formatted', '—')}")

@main.command()
@click.option('--trash', is_flag=True, help='Scan system Trash for deleted files')
@click.option('--restore-trash', is_flag=True, help='Restore files from system trash (requires --trash)')
@click.option('--carve', type=click.Path(exists=True), help='Carve files from a disk image / device path')
@click.option('--out', type=click.Path(), help='Output directory for carved files')
@click.option('--types', help='Comma-separated file extensions to carve (e.g. jpg,png,pdf)')
def recover(trash, restore_trash, carve, out, types):
    """Recover deleted files from trash or carve from disk images."""
    import os
    from .modules.recovery import scan_trash, restore_from_trash, carve_files_from_image, TrashScanUnsupported

    if trash:
        click.echo("Scanning system Trash...")
        try:
            items = scan_trash()
        except TrashScanUnsupported as exc:
            click.echo(f"Trash scan unavailable: {exc}", err=True)
            return
        click.echo(f"Found {len(items)} files in trash:")
        for idx, item in enumerate(items[:15]):
            click.echo(f"  [{idx}] {item['filename']} (Original: {item['original_path']})")
        if len(items) > 15:
            click.echo(f"  ... and {len(items) - 15} more")
            
        if restore_trash and items:
            if click.confirm("\nDo you want to restore ALL files in trash?"):
                res = restore_from_trash(items)
                click.echo(f"Restore complete. Restored: {len(res.get('restored', []))} | Failed: {len(res.get('failed', []))}")
    elif carve:
        if not out:
            click.echo("Error: --out directory is required when carving.", err=True)
            return
        file_types = [t.strip().lower() for t in types.split(",")] if types else None
        click.echo(f"Carving files from {carve} to {out}...")
        result = carve_files_from_image(carve, out, file_types=file_types)
        if "error" in result:
            click.echo(f"Carving error: {result['error']}")
        else:
            click.echo(f"Carving complete. Recovered {len(result.get('carved', []))} files.")
    else:
        click.echo("Specify either --trash or --carve. Run 'fm recover --help' for details.")

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--edit', help='Set field=value (e.g. Artist="New Artist")')
@click.option('--strip', is_flag=True, help='Strip all metadata')
@click.option('--strip-gps', is_flag=True, help='Strip only GPS/location data')
def metadata(path, edit, strip, strip_gps):
    """Read, edit, or strip file metadata."""
    import os
    from .modules.metadata import MetadataEngine
    
    if not os.path.isfile(path):
        click.echo("Error: Metadata command requires a file path.", err=True)
        return
        
    if strip:
        res = MetadataEngine.remove_metadata(path, dry_run=False)
        if res.get("success"):
            click.echo("Metadata stripped successfully.")
        else:
            click.echo(f"Failed to strip metadata: {res.get('message')}")
    elif strip_gps:
        gps_fields = [
            "GPSLatitude", "GPSLongitude", "GPSAltitude",
            "GPSLatitudeRef", "GPSLongitudeRef", "GPSAltitudeRef",
            "GPSTimeStamp", "GPSDateStamp", "GPSVersionID",
        ]
        res = MetadataEngine.remove_metadata(path, fields=gps_fields, dry_run=False)
        if res.get("success"):
            click.echo("GPS data stripped successfully.")
        else:
            click.echo(f"Failed to strip GPS data: {res.get('message')}")
    elif edit:
        if "=" not in edit:
            click.echo("Error: --edit format must be field=value", err=True)
            return
        field, val = edit.split("=", 1)
        res = MetadataEngine.write_metadata(path, {field: val}, dry_run=False)
        if res.get("success"):
            click.echo(f"Successfully set {field}={val}")
        else:
            click.echo(f"Failed to write metadata: {res.get('message')}")
    else:
        # Read
        meta = MetadataEngine.read_metadata(path)
        click.echo(f"File: {meta.get('filename')}")
        click.echo(f"Handler: {meta.get('handler')}")
        if meta.get("has_gps"):
            gps = meta.get("gps", {})
            click.echo(f"GPS: Lat {gps.get('latitude')}, Lon {gps.get('longitude')}")
        fields = meta.get("fields", {})
        if fields:
            click.echo("\nMetadata Fields:")
            for k, v in fields.items():
                click.echo(f"  {k}: {v}")
        else:
            click.echo("\nNo metadata fields found.")

@main.command()
@click.option('--export', type=click.Choice(['json', 'html']), help='Export format')
@click.option('--out', type=click.Path(), help='Output file path for export')
def hardware(export, out):
    """Display comprehensive system hardware diagnostics."""
    from .modules.hardware import get_hardware_report, get_upgrade_recommendations, export_hardware_report
    from .core.utils import format_size
    
    click.echo("Running hardware diagnostics...")
    report = get_hardware_report()
    
    if export:
        if not out:
            click.echo("Error: --out file path is required when exporting.", err=True)
            return
        export_hardware_report(report, out, fmt=export)
        click.echo(f"Report exported to {out}")
    else:
        sys_info = report.get("system", {})
        cpu_info = report.get("cpu", {})
        ram_info = report.get("ram", {})
        click.echo("\nHardware Profile:")
        click.echo(f"  OS: {sys_info.get('os')} {sys_info.get('os_release')} ({sys_info.get('distro', '—')})")
        click.echo(f"  Motherboard: {report.get('motherboard', {}).get('board_vendor', '—')} {report.get('motherboard', {}).get('board_name', '—')}")
        click.echo(f"  CPU: {cpu_info.get('model')}")
        click.echo(f"    Cores: {cpu_info.get('physical_cores')} physical, {cpu_info.get('logical_cores')} logical")
        click.echo(f"    Frequency: {cpu_info.get('frequency_mhz')} MHz")
        click.echo(f"  Memory (RAM): {ram_info.get('formatted_total')} total")
        
        click.echo("\nStorage Devices:")
        for dev in report.get("storage", {}).get("devices", []):
            click.echo(f"  - {dev.get('name')}: {dev.get('model')} ({dev.get('size')}) [{dev.get('type')}]")
            
        gpus = report.get("gpu", [])
        if gpus:
            click.echo("\nGPU(s):")
            for gpu in gpus:
                click.echo(f"  - {gpu.get('name')} ({gpu.get('vram') or 'Unknown VRAM'})")
                
        recs = get_upgrade_recommendations(report)
        if recs:
            click.echo("\nUpgrade Recommendations:")
            for rec in recs:
                click.echo(f"  💡 {rec}")

@main.command()
@click.argument('path', type=click.Path(exists=True), required=False)
@click.option('--parse-artifacts', is_flag=True, help='Parse OS artifacts')
@click.option('--search-keyword', help='Search for a specific keyword in files')
@click.option('--list-types', is_flag=True, help='List known file-signature categories used for type identification and carving')
def forensics(path, parse_artifacts, search_keyword, list_types):
    """Forensic utilities for artifact parsing and keyword search."""
    from .modules.forensics import parse_os_artifacts, keyword_search

    if list_types:
        from .modules.file_signatures import get_all_categories
        categories = get_all_categories()
        click.echo("Known file-signature categories:")
        for category, formats in categories.items():
            click.echo(f"  {category}: {', '.join(formats)}")
        return

    if not path:
        click.echo("Error: PATH is required unless --list-types is used.", err=True)
        return

    if parse_artifacts:
        click.echo(f"Parsing OS artifacts from {path}...")
        artifacts = parse_os_artifacts(path)
        for cat, data in artifacts.items():
            count = len(data) if isinstance(data, list) else 1 if data else 0
            click.echo(f"  {cat.replace('_', ' ').title()}: {count} items found")
    elif search_keyword:
        click.echo(f"Searching for keyword '{search_keyword}' in {path}...")
        results = keyword_search([path], [search_keyword])
        click.echo(f"Found {len(results)} matches:")
        for res in results[:20]:
            click.echo(f"  {res['path']}: Line {res['line_number']} (Offset 0x{res.get('offset', 0):X})")
    else:
        click.echo("Specify --parse-artifacts, --search-keyword, or --list-types. Run 'fm forensics --help' for details.")

@main.command()
@click.option('--info', 'mount_point', help='Show detailed usage info for a specific mount point')
def devices(mount_point):
    """List connected storage devices and their usage."""
    from .modules.device_manager import list_storage_devices, get_device_info

    if mount_point:
        details = get_device_info(mount_point)
        if not details:
            click.echo(f"Error: '{mount_point}' is not a valid or accessible mount point.", err=True)
            return
        click.echo(f"Mount point: {details.get('mountpoint')}")
        click.echo(f"Device: {details.get('device', '\u2014')}")
        click.echo(f"Type: {details.get('type', '\u2014')}")
        click.echo(f"Filesystem: {details.get('fstype', '\u2014')}")
        if 'formatted_total' in details:
            click.echo(f"Usage: {details.get('formatted_used')} used / {details.get('formatted_total')} total ({details.get('percent_used', 0)}%)")
        if 'error' in details:
            click.echo(f"Note: {details['error']}")
        return

    devices_list = list_storage_devices()
    if not devices_list:
        click.echo("No storage devices detected.")
        return

    click.echo(f"{'Mountpoint':<25}{'Type':<18}{'Filesystem':<12}{'Used':<12}{'Total':<12}")
    for dev in devices_list:
        used = dev.get('formatted_used', '\u2014')
        total = dev.get('formatted_total', '\u2014')
        click.echo(f"{dev.get('mountpoint', '\u2014')[:24]:<25}{dev.get('type', '\u2014'):<18}{dev.get('fstype', '\u2014'):<12}{used:<12}{total:<12}")

@main.command('hash-calc')
@click.argument('paths', type=click.Path(exists=True), nargs=-1, required=True)
@click.option('--algo', type=click.Choice(['md5', 'sha1', 'sha256', 'sha512']), default='sha256', help='Hash algorithm')
def hash_calc(paths, algo):
    """Calculate cryptographic hashes of files."""
    from .modules.forensics import calculate_hashes
    
    results = calculate_hashes(paths, algorithms=[algo])
    for res in results:
        click.echo(f"{res[algo]}\t{res['filename']}")

if __name__ == '__main__':
    main()
