import json
import os
import sys
import urllib.parse
import urllib.request


def run_ci_audit():
    """
    CI/CD Accessibility Audit Script.
    Sends a target URL or local HTML files to the QA Accessibility API
    and fails the build if critical or high accessibility issues are found.
    """
    api_url = os.environ.get("A11Y_API_URL", "http://localhost:8001")
    target_url = os.environ.get("A11Y_TARGET_URL")

    if not target_url:
        print("[CI/CD A11y] Error: A11Y_TARGET_URL environment variable is not set.")
        sys.exit(1)

    print(f"[CI/CD A11y] Connecting to API: {api_url}")
    print(f"[CI/CD A11y] Auditing target URL: {target_url}")

    # Prepare payload for API
    payload = {
        "url": target_url
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req_url = f"{api_url}/analyze/url"
        req = urllib.request.Request(req_url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=120) as response:
            res_data = json.loads(response.read().decode("utf-8"))

        if not res_data.get("success"):
            print(f"[CI/CD A11y] Error: API request failed. Details: {res_data.get('error')}")
            sys.exit(1)

        # Parse issues
        issues = res_data.get("data", {}).get("issues", [])
        print(f"[CI/CD A11y] Audit finished. Found {len(issues)} total issues.")

        # Filter critical/high failures
        failed_gates = []
        for issue in issues:
            severity = issue.get("severity", "").lower()
            if severity in ("critical", "high"):
                failed_gates.append(issue)

        if failed_gates:
            print("\n" + "="*80)
            print("  ACCESSIBILITY BUILD GATE FAILED (WCAG 2.2 Compliance)")
            print("="*80)
            for idx, issue in enumerate(failed_gates, 1):
                print(f"[{idx}] {issue.get('severity').upper()} - Criterion: {issue.get('criterion')}")
                print(f"    Element: {issue.get('element')}")
                print(f"    Description: {issue.get('description')}")
                print(f"    Remediation: {issue.get('suggestion')}\n")

            print(f"[CI/CD A11y] Build blocked. Found {len(failed_gates)} CRITICAL/HIGH violations.")
            sys.exit(1)

        print("[CI/CD A11y] Success! All accessibility build gates passed (No CRITICAL/HIGH violations).")
        sys.exit(0)

    except Exception as exc:
        print(f"[CI/CD A11y] Connection or API error occurred: {exc}")
        print("[CI/CD A11y] Make sure your qaaccessibility server is running and accessible.")
        sys.exit(1)

if __name__ == "__main__":
    run_ci_audit()
