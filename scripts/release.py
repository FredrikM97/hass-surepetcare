#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys

PYPROJECT_PATH = "pyproject.toml"
GITHUB_REPO = "https://github.com/FredrikM97/hass-surepetcare"

# ANSI color codes
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
RESET = "\033[0m"

REQUIRED_CLI_TOOLS = ["bump-my-version"]

def git(*args, capture_output=False):
    """Run a git command and optionally capture its output."""
    cmd = ["git"] + list(args)
    if capture_output:
        return subprocess.check_output(cmd).decode().strip()
    subprocess.run(cmd, check=True)

def confirm(question, default="n"):
    """Prompt the user for a yes/no confirmation with colored prompt."""
    yn = "[y/N]" if default.lower() == "n" else "[Y/n]"
    answer = input(f"{BOLD}{question} {yn}: {RESET}").strip().lower()
    if not answer:
        answer = default.lower()
    return answer == "y"

def check_cli_tools():
    """Verify that all required CLI tools are installed, else exit with instructions."""
    for tool in REQUIRED_CLI_TOOLS:
        if shutil.which(tool) is None:
            print(
                f"{RED}Missing required command: {tool}{RESET}\n"
                f"Install it with: {CYAN}pip install {tool.replace('-', '_')}{RESET}"
            )
            sys.exit(1)

def get_bump_options():
    """Return a list of available version bump options from bump-my-version."""
    output = subprocess.check_output(["bump-my-version", "show-bump"]).decode()
    options = []
    for line in output.splitlines():
        line = line.strip()
        if (
            "─ major ─" in line
            or "─ minor ─" in line
            or "─ patch ─" in line
            or "─ pre_l ─" in line
        ):
            parts = [p.strip() for p in line.split("─")]
            if len(parts) >= 3:
                bump_type = parts[-2]
                version = parts[-1]
                valid = "invalid" not in version and bump_type != "pre_n"
                if valid:
                    options.append((bump_type, version))
    return options

def select_bump_option(bump_options):
    """Prompt the user to select a version bump option from the available list."""
    print(f"\n{BOLD}Available version bumps:{RESET}")
    for idx, (bump_type, version) in enumerate(bump_options, 1):
        print(
            f"  {CYAN}{idx}.{RESET} {YELLOW}{bump_type:7}{RESET} → {GREEN}{version}{RESET}"
        )
    while True:
        try:
            choice = int(input(f"{BOLD}Select bump type [1]: {RESET}") or 1)
            if 1 <= choice <= len(bump_options):
                return bump_options[choice - 1]
            else:
                print(
                    f"{YELLOW}Invalid selection. Please choose a valid bump type.{RESET}"
                )
        except Exception:
            print(f"{YELLOW}Invalid input. Please enter a number.{RESET}")

def dry_run_bump(bump_type, new_version=None):
    """Perform a dry run of the version bump and print the output."""
    print(
        f"\n{BOLD}Dry run for bump-my-version bump:{RESET} {YELLOW}{bump_type}{RESET}"
    )
    cmd = ["bump-my-version", "bump", bump_type, "--dry-run"]
    if new_version:
        cmd += ["--new-version", new_version]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
        print(output)
        return True
    except subprocess.CalledProcessError as e:
        print(f"{RED}Dry run failed. Output:{RESET}")
        print(e.output.decode() if e.output else "")
        return False

def do_bump(bump_type, new_version=None):
    """Perform the actual version bump (no tag created)."""
    cmd = ["bump-my-version", "bump", bump_type, "--no-tag"]
    if new_version:
        cmd += ["--new-version", new_version]
    subprocess.run(cmd, check=True)

def get_latest_final_tag():
    """Return the latest final release tag (vX.Y.Z) sorted by version."""
    tags = git(
        "tag",
        "--list",
        "v[0-9]*.[0-9]*.[0-9]*",
        "--sort=-v:refname",
        capture_output=True,
    ).splitlines()
    if not tags:
        print(f"{RED}No final release tags found.{RESET}")
        sys.exit(1)
    return tags[0]

def get_commit_for_tag(tag):
    """Return the commit SHA for a given tag."""
    return git("rev-list", "-n", "1", tag, capture_output=True)

def summarize_commits_between(ref1, ref2):
    """Print and return the number of commits between two refs."""
    log = git("log", "--oneline", f"{ref1}..{ref2}", capture_output=True)
    if log:
        commits = log.splitlines()
        print(
            f"\n{BOLD}Total commits between {CYAN}{ref1[:7]}{RESET} "
            f"and {CYAN}{ref2[:7]}{RESET}: {YELLOW}{len(commits)}{RESET}"
        )
        for c in commits:
            print(f"  {c}")
        return commits
    else:
        print(f"\n{YELLOW}No commits between {ref1[:7]} and {ref2[:7]}.{RESET}")
        return []

def delete_branch(branch):
    """Delete a local git branch if it exists."""
    branches = git("branch", capture_output=True).replace("*", "").split()
    if branch in branches:
        git("branch", "-D", branch)

def force_fetch_dev():
    """Force fetch the dev branch from origin."""
    git("fetch", "origin", "dev:dev", "--force")

def tag_and_bump_on_branch():
    """Guide the user through selecting a version bump and create a release branch for it."""
    check_cli_tools()
    print(
        f"\n{BOLD}Release type options:{RESET}\n"
        f"  1. Final release ({CYAN}plain version, e.g. x.y.z{RESET})\n"
        f"  2. Dev release   ({CYAN}dev version, e.g. x.y.z-dev0{RESET})"
    )
    release_type = input(f"{BOLD}Select release type [1]: {RESET}").strip() or "1"

    bump_options = get_bump_options()
    if not bump_options:
        print(f"{RED}No valid bump options available.{RESET}")
        sys.exit(1)

    if release_type == "1":
        bumps = [opt for opt in bump_options if opt[0] in {"patch", "minor", "major"}]
        if not bumps:
            print(f"{RED}No valid final bump options available.{RESET}")
            sys.exit(1)
        selected_type, version = select_bump_option(bumps)
    else:
        selected_type, version = select_bump_option(bump_options)

    if not dry_run_bump(selected_type):
        print(f"{RED}Aborted due to dry run failure.{RESET}")
        sys.exit(1)
    if not confirm(f"Proceed with version bump to {CYAN}{version}{RESET}?"):
        print(f"{YELLOW}Aborted.{RESET}")
        sys.exit(0)

    # Get the last release tag and its commit
    last_tag = get_latest_final_tag()
    last_commit = get_commit_for_tag(last_tag)
    print(f"{BOLD}Last release tag:{RESET} {CYAN}{last_tag}{RESET} at {YELLOW}{last_commit[:7]}{RESET}")

    # Get the commit to merge (usually latest on dev)
    dev_branch = "dev"
    git("fetch", "origin")
    git("checkout", dev_branch)
    git("pull", "origin", dev_branch)
    dev_commit = git("rev-parse", dev_branch, capture_output=True)
    print(f"{BOLD}Latest dev commit:{RESET} {YELLOW}{dev_commit[:7]}{RESET}")

    # Summarize commits that will be included
    summarize_commits_between(last_commit, dev_commit)

    # Create a new release branch from the last tag
    release_branch = f"release-v{version}"
    print(f"{BOLD}Creating release branch {GREEN}{release_branch}{RESET} from {CYAN}{last_tag}{RESET}...")
    try:
        git("checkout", "-b", release_branch, last_commit)

        # Merge changes from dev into the release branch (preserve all commits)
        print(f"{BOLD}Merging changes from {CYAN}{dev_branch}{RESET} into {GREEN}{release_branch}{RESET}...{RESET}")
        git("merge", "--no-ff", dev_commit)

        # Run the version bump on the release branch
        print(f"{BOLD}Running version bump on {GREEN}{release_branch}{RESET}...{RESET}")
        do_bump(selected_type)
        git("add", ".")
        git("commit", "-m", f"Bump version for release")
        git("push", "-u", "origin", release_branch)
        print(f"{GREEN}✔ Release branch {release_branch} created and pushed with version bump.{RESET}")

        print(
            f"\n{BOLD}Next steps:{RESET}\n"
            f"  1. Open a PR from {CYAN}{release_branch}{RESET} to {CYAN}main{RESET} on GitHub.\n"
            f"  2. Use the {YELLOW}Squash and merge{RESET} option when merging the PR if you want a single commit in main.\n"
            f"  3. Tag the release in main after merging, if desired.\n"
        )
    except Exception as e:
        print(f"\n{RED}Error during merge: {e}{RESET}")
        delete_branch(release_branch)
        force_fetch_dev()
        print(
            f"{YELLOW}Cleanup complete. Please resolve any issues before retrying.{RESET}"
        )
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Release flow for hass-surepetcare (merge all changes between last tag and dev into release branch)."
    )
    parser.add_argument(
        "--tag", action="store_true", help="Run the tag/bump step and create release branch"
    )
    args = parser.parse_args()

    if args.tag or True:
        tag_and_bump_on_branch()