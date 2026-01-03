"""Archive utility script for stats.csv and history.log.

Moves entries strictly older than 6 months to yearly archive files in _archive/_data/.
Also sorts the PocketTube database alphabetically.
"""

# Standard library
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Disable logging BEFORE importing yrt modules
os.environ['YRT_NO_LOGGING'] = '1'

# Third-party
import pandas as pd
from dateutil.relativedelta import relativedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Local (imported after setting YRT_NO_LOGGING)
from yrt import paths
from yrt.youtube import create_service_local, sort_db

# Constants
MONTHS_TO_ARCHIVE = 6
LOG_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S%z'

# Numeric columns that should be saved as integers (not floats)
NUMERIC_COLUMNS = [
    'duration',
    'views_w1', 'views_w4', 'views_w12', 'views_w24',
    'likes_w1', 'likes_w4', 'likes_w12', 'likes_w24',
    'comments_w1', 'comments_w4', 'comments_w12', 'comments_w24',
]


def get_cutoff_date() -> datetime:
    """Calculate the cutoff date for archiving.

    Returns:
        Timezone-aware datetime 6 months ago from today.
    """
    now = datetime.now(timezone.utc)
    return now - relativedelta(months=MONTHS_TO_ARCHIVE)


def convert_to_nullable_int(df: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric columns to nullable integer type.

    This ensures integers are saved without decimal points in CSV output,
    while still allowing NaN/empty values.

    Args:
        df: DataFrame to convert.

    Returns:
        DataFrame with numeric columns converted to Int64.
    """
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype('Int64')
    return df


def get_existing_video_ids(archive_path: Path) -> set[str]:
    """Load existing video IDs from an archive file.

    Args:
        archive_path: Path to the archive CSV file.

    Returns:
        Set of video IDs already in the archive.
    """
    if not archive_path.exists():
        return set()

    try:
        df = pd.read_csv(archive_path)
        return set(df['video_id'].astype(str))
    except (pd.errors.EmptyDataError, KeyError):
        return set()


def archive_stats(cutoff: datetime) -> tuple[int, int]:
    """Archive stats.csv entries older than cutoff date.

    Args:
        cutoff: Entries strictly older than this date will be archived.

    Returns:
        Tuple of (archived_count, skipped_duplicates_count).
    """
    stats_path = paths.STATS_CSV

    if not stats_path.exists():
        print(f"  Stats file not found: {stats_path}")
        return 0, 0

    # Load stats
    df = pd.read_csv(stats_path)
    if df.empty:
        print("  Stats file is empty.")
        return 0, 0

    # Parse release_date to datetime
    df['release_date_parsed'] = pd.to_datetime(df['release_date'], utc=True)

    # Split into archive and keep
    to_archive = df[df['release_date_parsed'] < cutoff].copy()
    to_keep = df[df['release_date_parsed'] >= cutoff].copy()

    if to_archive.empty:
        print("  No stats entries older than 6 months to archive.")
        return 0, 0

    # Group by year
    to_archive['year'] = to_archive['release_date_parsed'].dt.year
    archived_count = 0
    skipped_count = 0

    for year, year_df in to_archive.groupby('year'):
        year_dir = paths.ARCHIVE_DATA_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        archive_file = year_dir / f'stats_{year}.csv'

        # Get existing video IDs to avoid duplicates
        existing_ids = get_existing_video_ids(archive_file)

        # Filter out duplicates
        year_df_clean = year_df[~year_df['video_id'].astype(str).isin(existing_ids)]
        year_skipped = len(year_df) - len(year_df_clean)
        skipped_count += year_skipped

        if year_df_clean.empty:
            print(f"    {year}: All {len(year_df)} entries already in archive (skipped)")
            continue

        # Drop helper columns before saving
        year_df_clean = year_df_clean.drop(columns=['release_date_parsed', 'year'])

        # Convert numeric columns to nullable int for proper formatting
        year_df_clean = convert_to_nullable_int(year_df_clean)

        # Append to archive (or create new file)
        if archive_file.exists():
            # Ensure file ends with newline before appending
            with open(archive_file, 'rb') as f:
                f.seek(-1, 2)  # Go to last byte
                if f.read(1) != b'\n':
                    with open(archive_file, 'a', encoding='utf-8') as fa:
                        fa.write('\n')
            year_df_clean.to_csv(archive_file, mode='a', header=False, index=False)
        else:
            year_df_clean.to_csv(archive_file, mode='w', header=True, index=False)

        archived_count += len(year_df_clean)
        print(f"    {year}: Archived {len(year_df_clean)} entries" +
              (f" (skipped {year_skipped} duplicates)" if year_skipped > 0 else ""))

    # Overwrite source with remaining entries
    to_keep = to_keep.drop(columns=['release_date_parsed'])
    to_keep = convert_to_nullable_int(to_keep)
    to_keep.to_csv(stats_path, index=False)

    return archived_count, skipped_count


def parse_log_timestamp(line: str) -> datetime | None:
    """Parse timestamp from a log line.

    Args:
        line: A log line starting with a timestamp.

    Returns:
        Parsed datetime or None if parsing fails.
    """
    try:
        # Extract timestamp part (first 24 characters: "2025-01-01 08:14:02+0000")
        timestamp_str = line[:24]
        return datetime.strptime(timestamp_str, LOG_TIMESTAMP_FORMAT)
    except (ValueError, IndexError):
        return None


def archive_logs() -> int:
    """Archive history.log lines from previous years.

    Keeps only current year logs in the source file, archiving all previous years.

    Returns:
        Number of lines archived.
    """
    log_path = paths.HISTORY_LOG
    current_year = datetime.now(timezone.utc).year

    if not log_path.exists():
        print(f"  Log file not found: {log_path}")
        return 0

    # Read all lines (handle encoding errors gracefully)
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    if not lines:
        print("  Log file is empty.")
        return 0

    # Split into archive (previous years) and keep (current year)
    to_archive: dict[int, list[str]] = defaultdict(list)
    to_keep: list[str] = []
    malformed_count = 0

    for line in lines:
        timestamp = parse_log_timestamp(line)

        if timestamp is None:
            # Keep malformed lines in source (don't lose data)
            to_keep.append(line)
            malformed_count += 1
            continue

        year = timestamp.year
        if year < current_year:
            to_archive[year].append(line)
        else:
            to_keep.append(line)

    if malformed_count > 0:
        print(f"  Warning: {malformed_count} malformed lines kept in source file")

    if not to_archive:
        print("  No log entries from previous years to archive.")
        return 0

    archived_count = 0

    # Archive by year
    for year, year_lines in sorted(to_archive.items()):
        year_dir = paths.ARCHIVE_DATA_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        archive_file = year_dir / f'history_{year}.log'

        # Append to archive
        with open(archive_file, 'a', encoding='utf-8') as f:
            f.writelines(year_lines)

        archived_count += len(year_lines)
        print(f"    {year}: Archived {len(year_lines)} log lines")

    # Overwrite source with remaining lines
    with open(log_path, 'w', encoding='utf-8') as f:
        f.writelines(to_keep)

    return archived_count


def main() -> None:
    """Main function to run the archiving process."""
    cutoff = get_cutoff_date()

    print("=" * 60)
    print("YouTube Release Tracker - Data Archive Utility")
    print("=" * 60)
    current_year = datetime.now(timezone.utc).year
    print(f"Current date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Stats cutoff: {cutoff.strftime('%Y-%m-%d')} (entries older than {MONTHS_TO_ARCHIVE} months)")
    print(f"Logs cutoff:  Year < {current_year} (previous years)\n")

    # Archive stats
    print("Archiving stats.csv...")
    stats_archived, stats_skipped = archive_stats(cutoff)
    print()

    # Archive logs
    print("Archiving history.log...")
    logs_archived = archive_logs()
    print()

    # Sort PocketTube database
    print("Sorting PocketTube database...")
    try:
        service = create_service_local(log=False)
        sort_db(service=service, log=False)
        db_sorted = True

    except Exception as e:
        print(f"  Failed to sort database: {e}")
        db_sorted = False
    print()

    # Summary
    print("=" * 60)
    print("Summary:")
    print(f"  Stats entries archived: {stats_archived}")

    if stats_skipped > 0:
        print(f"  Stats duplicates skipped: {stats_skipped}")

    print(f"  Log lines archived: {logs_archived}")
    print(f"  Database sorted: {'Yes' if db_sorted else 'No'}")
    print("=" * 60)


if __name__ == '__main__':
    main()
