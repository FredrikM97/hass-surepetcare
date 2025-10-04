#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
import textwrap

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
        if "─ major ─" in line or "─ minor ─" in line or "─ patch ─" in line or "─ pre_l ─" in line:
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
        print(f"  {CYAN}{idx}.{RESET} {YELLOW}{bump_type:7}{RESET} → {GREEN}{version}{RESET}")
    while True:
        try:
            choice = int(input(f"{BOLD}Select bump type [1]: {RESET}") or 1)
            if 1 <= choice <= len(bump_options):
                return bump_options[choice - 1]
            else:
                print(f"{YELLOW}Invalid selection. Please choose a valid bump type.{RESET}")
        except Exception:
            print(f"{YELLOW}Invalid input. Please enter a number.{RESET}")


def dry_run_bump(bump_type, new_version=None):
    """Perform a dry run of the version bump and print the output."""
    print(f"\n{BOLD}Dry run for bump-my-version bump:{RESET} {YELLOW}{bump_type}{RESET}")
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
        "tag", "--list", "v[0-9]*.[0-9]*.[0-9]*", "--sort=-v:refname", capture_output=True
    ).splitlines()
    if not tags:
        print(f"{RED}No final release tags found.{RESET}")
        sys.exit(1)
    return tags[0]


def get_commit_for_tag(tag):
    """Return the commit SHA for a given tag."""
    return git("rev-list", "-n", "1", tag, capture_output=True)


def get_current_version(pyproject_path=PYPROJECT_PATH):
    """Extract and return the current version from pyproject.toml."""
    with open(pyproject_path) as f:
        for line in f:
            m = re.match(r'version\s*=\s*["\']([^"\']+)["\']', line)
            if m:
                return m.group(1)
    print(f"{RED}Could not find version in pyproject.toml{RESET}")
    sys.exit(1)


def get_commit_for_version(version, pyproject_path=PYPROJECT_PATH):
    """Find the commit SHA where the given version was set in pyproject.toml."""
    log = subprocess.check_output(["git", "log", "--pretty=format:%H", pyproject_path]).decode().splitlines()
    for sha in log:
        content = git("show", f"{sha}:{pyproject_path}", capture_output=True)
        if f'version = "{version}"' in content or f"version = '{version}'" in content:
            return sha
    print(f"{RED}Could not find commit for version {version}{RESET}")
    sys.exit(1)


def summarize_commits_between(ref1, ref2):
    """Print and return the number of commits between two refs."""
    log = git("log", "--oneline", f"{ref1}..{ref2}", capture_output=True)
    if log:
        commits = log.splitlines()
        print(
            f"\n{BOLD}Total commits between {CYAN}{ref1[:7]}{RESET} "
            f"and {CYAN}{ref2[:7]}{RESET}: {YELLOW}{len(commits)}{RESET}"
        )
        return commits
    else:
        print(f"\n{YELLOW}No commits between {ref1[:7]} and {ref2[:7]}.{RESET}")
        return []


def print_github_compare_link(from_commit, to_commit):
    """Print a GitHub compare link for the given commit SHAs."""
    if "<owner>/<repo>" in GITHUB_REPO:
        return
    print(
        f"\n{BOLD}GitHub compare:{RESET} "
        f"{CYAN}{GITHUB_REPO}/compare/{from_commit[:7]}..{to_commit[:7]}{RESET}"
    )


def delete_branch(branch):
    """Delete a local git branch if it exists."""
    branches = git("branch", capture_output=True).replace("*", "").split()
    if branch in branches:
        git("branch", "-D", branch)


def force_fetch_main():
    """Force fetch the main branch from origin."""
    git("fetch", "origin", "main:main", "--force")


def squash_between_commits(old_commit, new_commit, old_version, new_version, target_branch="main"):
    """Create a release branch and squash merge changes between two commits."""
    branch_name = f"release-v{new_version}"
    try:
        print(
            f"{BOLD}Creating branch {GREEN}{branch_name}{RESET} from "
            f"{CYAN}{old_commit[:7]}{RESET} (v{old_version})...\n"
            f"{BOLD}Squash merging {CYAN}{new_commit[:7]}{RESET} (v{new_version}) into "
            "{GREEN}{branch_name}{RESET}...{RESET}"
        )
        summarize_commits_between(old_commit, new_commit)
        print_github_compare_link(old_commit, new_commit)
        git("checkout", "-b", branch_name, old_commit)
        git("merge", "--squash", new_commit)
        status = git("status", "--porcelain", capture_output=True)
        if not status.strip():
            print(f"{YELLOW}No changes to commit after squash. Exiting.{RESET}")
            git("checkout", target_branch)
            delete_branch(branch_name)
            return False
        git("commit", "-m", f"Release: v{new_version}")
        print(f"{GREEN}Squash complete on branch {branch_name}.{RESET}")

        instructions = textwrap.dedent(
            f"""
            {BOLD}Next steps:{RESET}
              1. Push your branch and open a PR to '{target_branch}':
                 {CYAN}git push origin {branch_name}{RESET}
                 Then open a PR from '{branch_name}' to '{target_branch}'.

              2. After merge, tag the squashed commit in main:
                 {CYAN}git checkout main && git pull
                 git tag v{new_version} && git push origin v{new_version}{RESET}
        """
        )
        print(instructions)
        return True
    except Exception as e:
        print(f"\n{RED}Error during squash: {e}{RESET}")
        delete_branch(branch_name)
        force_fetch_main()
        print(f"{YELLOW}Cleanup complete. Please resolve any issues before retrying.{RESET}")
        sys.exit(1)


def tag_and_bump():
    """Guide the user through selecting and performing a version bump."""
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
    do_bump(selected_type)
    print(f"\n{GREEN}✔ Version bumped to {CYAN}{version}{RESET}")


def full_release_flow():
    """Run the full release flow: tag/bump, then squash and PR."""
    print(f"{BOLD}Step 1: Tag and push new version{RESET}")
    tag_and_bump()
    print(f"\n{BOLD}Step 2: Squash and prepare release PR{RESET}")
    if confirm("Continue to the squash/release process?"):
        main_release()
    else:
        print(
            f"\n{YELLOW}You can run the release process later with:{RESET} "
            f"{CYAN}python3 full_release.py --release{RESET}"
        )
    print(f"\n{GREEN}Full release flow complete! 🎉{RESET}")


def main_release():
    """Run only the squash and PR step of the release flow."""
    from_tag = get_latest_final_tag()
    from_commit = get_commit_for_tag(from_tag)
    from_version = from_tag.lstrip("v")
    to_version = get_current_version()
    to_commit = get_commit_for_version(to_version)
    parent_commit = git("rev-parse", f"{to_commit}^", capture_output=True)

    print(
        f"\n{BOLD}Squashing from {YELLOW}v{from_version}{RESET} [{CYAN}{from_tag}{RESET}] "
        f"to {YELLOW}v{to_version}{RESET} [latest bump]:{RESET}"
    )
    commits = summarize_commits_between(from_commit, to_commit)

    print(f"\n{BOLD}Local diff for version bump commit:{RESET}")
    diffstat = git("diff", "--stat", parent_commit, to_commit, capture_output=True)
    print(diffstat if diffstat else f"{YELLOW}No changes in version bump commit.{RESET}")

    if not commits:
        print(f"{YELLOW}No changes to squash between these commits.{RESET}")
        sys.exit(0)
    if not confirm(
        f"Proceed with squash of all changes from version {from_version} to {to_version}?", default="n"
    ):
        print(f"{YELLOW}Aborted.{RESET}")
        sys.exit(0)
    squash_between_commits(from_commit, to_commit, from_version, to_version, target_branch="main")
    print(f"\n{GREEN}Release process complete! 🎉{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full release flow for hass-surepetcare.")
    parser.add_argument("--release", action="store_true", help="Only run the squash/release step")
    parser.add_argument("--tag", action="store_true", help="Only run the tag/bump step")
    args = parser.parse_args()

    if args.release:
        main_release()
    elif args.tag:
        tag_and_bump()
    else:
        full_release_flow()
