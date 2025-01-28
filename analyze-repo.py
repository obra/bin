 #!/usr/bin/env python3
import subprocess
import re
from collections import defaultdict
import argparse
from typing import Dict, Set, Tuple, List, Optional
import multiprocessing
from functools import partial
from dataclasses import dataclass
from datetime import datetime
import fnmatch
import os
import json
from email.utils import parseaddr

@dataclass
class LineInfo:
    content: str
    line_number: int
    last_modified: str  # Added to track when the line was last modified

@dataclass
class FileContribution:
    current_lines: List[LineInfo]
    historical_lines: int
    last_modified: Optional[str] = None  # Added to track file's last modification
    committer_email: Optional[str] = None  # Added to track committer's email

    def __init__(self):
        self.current_lines = []
        self.historical_lines = 0
        self.last_modified = None
        self.committer_email = None



class GitContributorAnalyzer:
    def __init__(self, repo_path: str, exclude_commits: List[str] = None,
                 exclude_paths: List[str] = None, exclude_patterns: List[str] = None):
        self.repo_path = repo_path
        self.exclude_commits = [c.strip() for c in (exclude_commits or [])]
        # Clean up paths, removing trailing slashes and empty entries
        self.exclude_paths = [p.strip('/') for p in (exclude_paths or []) if p.strip()]
        self.exclude_patterns = exclude_patterns or []
        self.contributor_stats: Dict[str, Dict[str, FileContribution]] = {}
        self.contributor_emails: Dict[str, Set[str]] = defaultdict(set)
        self.contributor_companies: Dict[str, Set[str]] = defaultdict(set)

    def get_revision_range(self) -> List[str]:
        """
        Construct the git revision range for analysis, excluding specified commits.
        Returns a list of revision arguments suitable for git commands.
        """
        if not self.exclude_commits:
            return ['HEAD']
        
        # Return HEAD and each exclusion as separate arguments
        return ['HEAD'] + [f'^{commit}' for commit in self.exclude_commits]

    def analyze_repository(self, file_extensions: Set[str] = None) -> None:
        try:
            # Modified to properly pass revision range as separate arguments
            cmd = ['git', '-C', self.repo_path, 'ls-tree', '-r', '--name-only'] + self.get_revision_range()
            files = subprocess.check_output(cmd, text=True).split('\n')
        except subprocess.CalledProcessError as e:
            print(f"Error listing repository files: {str(e)}")
            return


    def should_exclude_file(self, file_path: str) -> bool:
        """Check if a file should be excluded based on path or pattern."""
        # Normalize the file path
        normalized_path = file_path.strip('/')
        
        # Debug output
        if os.environ.get('DEBUG'):
            print(f"\nChecking exclusion for: {normalized_path}")
            print(f"Exclude paths: {self.exclude_paths}")
        
        # Check exact path matches and directory prefixes
        for exclude_path in self.exclude_paths:
            # Convert both paths to use forward slashes for consistency
            exclude_path = exclude_path.replace('\\', '/')
            normalized_path = normalized_path.replace('\\', '/')
            
            # Check if the path matches exactly or if it's in an excluded directory
            if (normalized_path == exclude_path or 
                normalized_path.startswith(f"{exclude_path}/") or
                f"/{exclude_path}/" in f"/{normalized_path}/"):
                if os.environ.get('DEBUG'):
                    print(f"Excluded by path: {exclude_path}")
                return True
        
        # Check glob patterns
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(normalized_path, pattern):
                if os.environ.get('DEBUG'):
                    print(f"Excluded by pattern: {pattern}")
                return True
        
        return False

    def extract_email_domain(self, email: str) -> Optional[str]:
        """Extract domain from email address."""
        _, email_addr = parseaddr(email)
        try:
            return email_addr.split('@')[1] if '@' in email_addr else None
        except IndexError:
            return None


    @staticmethod
    def process_file(args) -> Tuple[str, Dict[str, Tuple[List[Tuple[int, str, str]], int, Optional[str], Optional[str]]]]:
        """Static method for parallel processing of files."""
        repo_path, revision_args, file_path = args
        result = defaultdict(lambda: ([], 0, None, None))
        
        try:
            # Modify the commands to use revision_args correctly
            show_cmd = ['git', '-C', repo_path, 'rev-list', '-1'] + revision_args + ['--', file_path]
            try:
                subprocess.check_output(show_cmd, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError:
                return file_path, {}

            # Modify blame command to use revision_args
            blame_cmd = [
                'git', '-C', repo_path,
                'blame', '--encoding=utf-8-strict',
                '--line-porcelain',
                '-w', '-M', '-C'
            ] + revision_args + ['--', file_path]
            
            try:
                blame_output = subprocess.check_output(blame_cmd, text=True, errors='replace')
            except subprocess.CalledProcessError:
                return file_path, {}

            current_author = None
            current_line_num = 0
            current_content = None
            current_date = None
            current_email = None
            
            for line in blame_output.split('\n'):
                if line.startswith('author '):
                    current_author = line[7:]
                elif line.startswith('author-mail '):
                    current_email = line[12:].strip('<>')
                elif line.startswith('author-time '):
                    current_date = datetime.fromtimestamp(int(line[12:])).strftime('%Y-%m-%d')
                elif line.startswith('\t'):
                    current_content = line[1:]
                    if current_author and current_content:
                        lines, count, _, email = result[current_author]
                        lines.append((current_line_num, current_content, current_date))
                        result[current_author] = (lines, count, current_date, current_email)
                        current_line_num += 1

            # Modify log command to use revision_args
            log_cmd = [
                'git', '-C', repo_path,
                'log', '--format=format:%aN%x00%aE',
                '--numstat'
            ] + revision_args + ['--', file_path]
            
            log_output = subprocess.check_output(log_cmd, text=True, errors='replace')
            current_author = None
            current_email = None
            
            for line in log_output.split('\n'):
                if not line.strip():
                    continue
                if not line[0].isdigit():
                    author_info = line.split('\x00')
                    current_author = author_info[0]
                    current_email = author_info[1] if len(author_info) > 1 else None
                else:
                    try:
                        additions, deletions, _ = line.split('\t')
                        if additions != '-':
                            lines, count, date, email = result[current_author]
                            result[current_author] = (lines, count + int(additions), date, current_email or email)
                    except ValueError:
                        continue

        except Exception as e:
            print(f"\nError processing {file_path}: {str(e)}")
            return file_path, {}

        return file_path, dict(result)

    def analyze_repository(self, file_extensions: Set[str] = None) -> None:
        try:
            # First, get the list of files from HEAD
            ls_files_cmd = ['git', '-C', self.repo_path, 'ls-files']
            if os.environ.get('DEBUG'):
                print(f"Running command: {' '.join(ls_files_cmd)}")
            
            files = subprocess.check_output(ls_files_cmd, text=True).split('\n')
            
            if os.environ.get('DEBUG'):
                print(f"Found {len(files)} files before filtering")

        except subprocess.CalledProcessError as e:
            print(f"Error listing repository files: {str(e)}")
            return

        # Filter files based on extensions and exclusion patterns
        files = [
            f for f in files if f and
            not self.should_exclude_file(f) and
            (not file_extensions or any(f.endswith(ext) for ext in file_extensions))
        ]

        if os.environ.get('DEBUG'):
            print(f"After path filtering: {len(files)} files")
            if len(files) == 0:
                print("No files remained after filtering!")
            else:
                print("First few files:")
                for f in files[:5]:
                    print(f"  {f}")

        # Prepare arguments for parallel processing
        args = [(self.repo_path, self.get_revision_range(), f) for f in files]

        # Process files in parallel
        cpu_count = multiprocessing.cpu_count()
        with multiprocessing.Pool(cpu_count) as pool:
            print(f"Processing {len(files)} files using {cpu_count} cores...")
            
            # Collect results
            for i, (file_path, file_results) in enumerate(pool.imap_unordered(self.process_file, args), 1):
                print(f"\rProcessed {i}/{len(files)} files", end='', flush=True)
                
                for author, (current_lines, historical_count, last_modified, email) in file_results.items():
                    if author not in self.contributor_stats:
                        self.contributor_stats[author] = {}
                    if file_path not in self.contributor_stats[author]:
                        self.contributor_stats[author][file_path] = FileContribution()
                    
                    contribution = self.contributor_stats[author][file_path]
                    contribution.historical_lines = historical_count
                    contribution.last_modified = last_modified
                    contribution.committer_email = email
                    contribution.current_lines.extend(
                        LineInfo(content, line_num, date) for line_num, content, date in current_lines
                    )
                    
                    if email:
                        self.contributor_emails[author].add(email)
                        domain = self.extract_email_domain(email)
                        if domain:
                            self.contributor_companies[author].add(domain)

        print("\nAnalysis complete!")


    def generate_report(self, output_file: str, output_format: str = 'txt', no_sample_code: bool = False) -> None:
        if output_format == 'json':
            self._generate_json_report(output_file)
        elif output_format == 'csv':
            self._generate_csv_report(output_file)
        else:
            self._generate_text_report(output_file, no_sample_code)

    def _generate_json_report(self, output_file: str) -> None:
        report_data = {
            'generated_at': datetime.now().isoformat(),
            'excluded_commits': self.exclude_commits,
            'excluded_paths': self.exclude_paths,
            'excluded_patterns': self.exclude_patterns,
            'contributors': {}
        }

        for author, file_stats in self.contributor_stats.items():
            current_total = sum(len(stats.current_lines) for stats in file_stats.values())
            historical_total = sum(stats.historical_lines for stats in file_stats.values())
            
            report_data['contributors'][author] = {
                'emails': list(self.contributor_emails[author]),
                'companies': list(self.contributor_companies[author]),
                'total_current_lines': current_total,
                'total_historical_lines': historical_total,
                'files': {}
            }

            for file_path, stats in file_stats.items():
                report_data['contributors'][author]['files'][file_path] = {
                    'current_lines': len(stats.current_lines),
                    'historical_lines': stats.historical_lines,
                    'last_modified': stats.last_modified,
                }

        with open(output_file, 'w') as f:
            json.dump(report_data, f, indent=2)

    def _generate_csv_report(self, output_file: str) -> None:
        """Generate a CSV report with contributor statistics."""
        import csv
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['Contributor Name', 'Email Addresses', 'Total Lines Contributed', 'Current Lines'])
            
            for author in sorted(self.contributor_stats.keys()):
                # Get all email addresses for this author
                emails = self.contributor_emails[author]
                email_list = ';'.join(sorted(emails)) if emails else ''
                
                # Calculate totals
                current_lines = 0
                historical_lines = 0
                
                for file_stats in self.contributor_stats[author].values():
                    current_lines += len(file_stats.current_lines)
                    historical_lines += file_stats.historical_lines
                
                writer.writerow([
                    author,
                    email_list,
                    historical_lines,
                    current_lines
                ])

    def _generate_text_report(self, output_file: str, no_sample_code: bool) -> None:
        with open(output_file, 'w') as f:
            f.write(f"Git Repository Contributor Analysis\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if self.exclude_commits:
                f.write("Excluded commits: " + ", ".join(self.exclude_commits) + "\n")
            if self.exclude_paths:
                f.write("Excluded paths: " + ", ".join(self.exclude_paths) + "\n")
            if self.exclude_patterns:
                f.write("Excluded patterns: " + ", ".join(self.exclude_patterns) + "\n")
            f.write("=" * 80 + "\n\n")

            # Calculate totals for sorting
            contributor_totals = []
            for author, file_stats in self.contributor_stats.items():
                current_total = sum(len(stats.current_lines) for stats in file_stats.values())
                historical_total = sum(stats.historical_lines for stats in file_stats.values())
                contributor_totals.append((author, current_total, historical_total))

            contributor_totals.sort(key=lambda x: x[1], reverse=True)

            for author, current_total, historical_total in contributor_totals:
                f.write(f"\nContributor: {author}\n")
                f.write("-" * 40 + "\n")
                
                # Write contact information
                if author in self.contributor_emails:
                    f.write("Contact Information:\n")
                    for email in sorted(self.contributor_emails[author]):
                        f.write(f"  Email: {email}\n")
                if author in self.contributor_companies:
                    f.write("Associated Companies/Organizations:\n")
                    for company in sorted(self.contributor_companies[author]):
                        f.write(f"  {company}\n")
                
                f.write(f"\nTotal lines currently in codebase: {current_total:,}\n")
                f.write(f"Total lines added historically: {historical_total:,}\n\n")

                file_stats = self.contributor_stats[author]
                if not no_sample_code:
                
                    # Current files and lines
                    f.write("Currently present lines by file:\n")
                    sorted_files = sorted(
                        file_stats.items(),
                        key=lambda x: len(x[1].current_lines),
                        reverse=True
                    )
                    
                    for file_path, stats in sorted_files:
                        if stats.current_lines:
                            f.write(f"  {file_path}: {len(stats.current_lines):,} lines")
                            if stats.last_modified:
                                f.write(f" (last modified: {stats.last_modified})\n")
                            else:
                                f.write("\n")
                            # Write first few lines as sample
                            for line in sorted(stats.current_lines, key=lambda x: x.line_number)[:3]:
                                content = line.content[:100]
                                f.write(f"    L{line.line_number+1} ({line.last_modified}): {content}")
                                if len(line.content) > 100:
                                    f.write("...")
                                f.write("\n")

                    # Historical contributions
                    f.write("\nHistorical line contributions by file:\n")
                    sorted_files = sorted(
                        file_stats.items(),
                        key=lambda x: x[1].historical_lines,
                        reverse=True
                    )
                    
                    for file_path, stats in sorted_files:
                        if stats.historical_lines > 0:
                            f.write(f"  {file_path}: {stats.historical_lines:,} lines\n")

                    f.write("\n" + "=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description='Analyze git repository for contributor line ownership')
    parser.add_argument('repo_path', help='Path to git repository')
    parser.add_argument('--extensions', help='Comma-separated list of file extensions to analyze (e.g., .cpp,.h)')
    parser.add_argument('--exclude-commits', help='Comma-separated list of commit hashes to exclude')
    parser.add_argument('--exclude-paths', help='Comma-separated list of paths to exclude (e.g., vendor/,lib/)')
    parser.add_argument('--exclude-patterns', help='Comma-separated list of glob patterns to exclude (e.g., *.min.js,*.generated.*)')
    parser.add_argument('--output', default='contributor-analysis.txt', help='Output file path for results')
    parser.add_argument('--format', choices=['txt', 'json','csv'], default='txt', help='Output format (default: txt)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--no-sample-code', action='store_true', help='Disable sample code output')
    args = parser.parse_args()

    if args.debug:
        os.environ['DEBUG'] = '1'
    
    file_extensions = set(args.extensions.split(',')) if args.extensions else None
    exclude_commits = args.exclude_commits.split(',') if args.exclude_commits else None
    exclude_paths = args.exclude_paths.split(',') if args.exclude_paths else None
    exclude_patterns = args.exclude_patterns.split(',') if args.exclude_patterns else None

    # Set the correct file extension if one isn't explicitly provided
    output_file = args.output
    if '.' not in os.path.basename(output_file):
        # No extension provided, add the appropriate one
        extensions = {
            'txt': '.txt',
            'json': '.json',
            'csv': '.csv'
        }
        output_file = output_file + extensions[args.format]
    
    analyzer = GitContributorAnalyzer(
        args.repo_path,
        exclude_commits,
        exclude_paths,
        exclude_patterns
    )
    analyzer.analyze_repository(file_extensions)
    analyzer.generate_report(output_file, args.format, args.no_sample_code)
    
    print(f"\nDetailed report written to {output_file}")

if __name__ == '__main__':
    main()
