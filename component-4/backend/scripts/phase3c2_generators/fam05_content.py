"""
Phase 3C.2 Family 05: Content Management, Markdown & Publishing (FAM-05-CONTENT).
Contains 50 scenarios:
- 12 Functional Bugs
- 6 Security Vulnerabilities
- 5 Performance Bottlenecks
- 5 Regressions
- 5 Integration Defects
- 4 Semantic Drift
- 3 Non-Convergent Repair
- 10 Clean Controls
"""
from typing import List
from scripts.phase3c2_generators.common import ScenarioSpec


def get_family_scenarios() -> List[ScenarioSpec]:
    scenarios: List[ScenarioSpec] = []
    idx = 1

    # -------------------------------------------------------------------------
    # 1. FUNCTIONAL BUGS (12 scenarios)
    # -------------------------------------------------------------------------
    # 1.1 Read time estimator calculation (words / 200 wpm)
    clean_code_1 = """def estimate_reading_time_minutes(word_count: int, wpm: int = 200) -> int:
    import math
    if word_count <= 0:
        return 0
    return math.ceil(word_count / wpm)
"""
    mut_code_1 = """def estimate_reading_time_minutes(word_count: int, wpm: int = 200) -> int:
    import math
    if word_count <= 0:
        return 0
    return math.floor(word_count / wpm)
"""
    oracle_1 = """def run_oracle():
    mins = estimate_reading_time_minutes(250, 200)
    assert mins == 2, f"Expected 2 minutes for 250 words, got {mins}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Reading Time Rounding Direction", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="ROUNDING_DIRECTION_INVERSION", clean_code=clean_code_1, mutated_code=mut_code_1,
        test_code=oracle_1, expected_behavior="Ceiling round reading time to give at least 1 min",
        observed_behavior="Floor rounds producing 1 min instead of 2 for 250 words", oracle_code=oracle_1
    ))
    idx += 1

    # 1.2 Article slug whitespace replacement
    clean_code_2 = """def generate_article_slug(title: str) -> str:
    cleaned = title.strip().lower()
    return "-".join(cleaned.split())
"""
    mut_code_2 = """def generate_article_slug(title: str) -> str:
    cleaned = title.strip().lower()
    return "_".join(cleaned.split())
"""
    oracle_2 = """def run_oracle():
    slug = generate_article_slug("Hello World Test")
    assert slug == "hello-world-test", f"Expected hyphen separated slug, got {slug}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Slug Separator Substitution", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="STRING_LITERAL_MUTATION", clean_code=clean_code_2, mutated_code=mut_code_2,
        test_code=oracle_2, expected_behavior="Join words with hyphens for SEO friendly URL slugs",
        observed_behavior="Joins words with underscores", oracle_code=oracle_2
    ))
    idx += 1

    # 1.3 Tag list deduplication preserving order
    clean_code_3 = """def deduplicate_tags(tags: list) -> list:
    seen = set()
    res = []
    for t in tags:
        norm = t.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            res.append(norm)
    return res
"""
    mut_code_3 = """def deduplicate_tags(tags: list) -> list:
    seen = set()
    res = []
    for t in tags:
        norm = t.strip().lower()
        if norm and norm in seen:
            seen.add(norm)
            res.append(norm)
    return res
"""
    oracle_3 = """def run_oracle():
    deduped = deduplicate_tags(["python", "ai", "python"])
    assert deduped == ["python", "ai"], f"Expected ['python', 'ai'], got {deduped}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tag Deduplication Membership Logic", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="MEMBERSHIP_OPERATOR_INVERSION", clean_code=clean_code_3, mutated_code=mut_code_3,
        test_code=oracle_3, expected_behavior="Keep first occurrence when NOT in seen",
        observed_behavior="Only keeps duplicates when IN seen", oracle_code=oracle_3
    ))
    idx += 1

    # 1.4 Excerpt truncation length boundary
    clean_code_4 = """def create_article_excerpt(content: str, max_chars: int = 100) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars].rstrip() + "..."
"""
    mut_code_4 = """def create_article_excerpt(content: str, max_chars: int = 100) -> str:
    if len(content) < max_chars:
        return content
    return content[:max_chars].rstrip() + "..."
"""
    oracle_4 = """def run_oracle():
    text = "A" * 100
    res = create_article_excerpt(text, 100)
    assert res == text, "Exact 100 char text must not be truncated with ellipsis"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Excerpt Length Boundary Inequality", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_4, mutated_code=mut_code_4,
        test_code=oracle_4, expected_behavior="Do not truncate when length equals max_chars",
        observed_behavior="Truncates text matching exact limit adding ellipsis", oracle_code=oracle_4
    ))
    idx += 1

    # 1.5 Markdown heading level extraction
    clean_code_5 = """def parse_heading_level(line: str) -> int:
    count = 0
    for char in line:
        if char == "#":
            count += 1
        else:
            break
    return count if (1 <= count <= 6) else 0
"""
    mut_code_5 = """def parse_heading_level(line: str) -> int:
    count = 0
    for char in line:
        if char == "#":
            count += 1
    return count if (1 <= count <= 6) else 0
"""
    oracle_5 = """def run_oracle():
    lvl = parse_heading_level("# Heading # with hash")
    assert lvl == 1, f"Expected 1 leading hash, got {lvl}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Markdown Leading Hash Parser", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=6,
        mutation_op="BREAK_STATEMENT_OMISSION", clean_code=clean_code_5, mutated_code=mut_code_5,
        test_code=oracle_5, expected_behavior="Stop counting hashes at first non-hash character",
        observed_behavior="Counts all hashes in entire line including title content", oracle_code=oracle_5
    ))
    idx += 1

    # 1.6 Word count minimum publishing requirement
    clean_code_6 = """def can_publish_article(word_count: int, min_words: int = 300) -> bool:
    return word_count >= min_words
"""
    mut_code_6 = """def can_publish_article(word_count: int, min_words: int = 300) -> bool:
    return word_count > min_words
"""
    oracle_6 = """def run_oracle():
    assert can_publish_article(300, 300) is True, "Exact 300 words meets minimum requirement"
    assert can_publish_article(299, 300) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Article Word Count Boundary Check", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RELATIONAL_OPERATOR_SUBSTITUTION", clean_code=clean_code_6, mutated_code=mut_code_6,
        test_code=oracle_6, expected_behavior="Allow publishing at exact word count threshold",
        observed_behavior="Rejects article meeting exact word count threshold", oracle_code=oracle_6
    ))
    idx += 1

    # 1.7 Prohibited word moderation filter
    clean_code_7 = """def contains_prohibited_terms(text: str, prohibited: set) -> bool:
    words = set(text.lower().split())
    return not words.isdisjoint(prohibited)
"""
    mut_code_7 = """def contains_prohibited_terms(text: str, prohibited: set) -> bool:
    words = set(text.lower().split())
    return words.isdisjoint(prohibited)
"""
    oracle_7 = """def run_oracle():
    assert contains_prohibited_terms("this is spam text", {"spam", "scam"}) is True, "Contains prohibited term 'spam'"
    assert contains_prohibited_terms("clean friendly article", {"spam", "scam"}) is False
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Content Moderation Disjoint Inversion", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="BOOLEAN_INVERSION", clean_code=clean_code_7, mutated_code=mut_code_7,
        test_code=oracle_7, expected_behavior="Return True when intersection is not empty",
        observed_behavior="Inverts detection marking clean text as prohibited and vice versa", oracle_code=oracle_7
    ))
    idx += 1

    # 1.8 Link protocol sanitizer
    clean_code_8 = """def is_safe_link(url: str) -> bool:
    allowed = ("http://", "https://", "mailto:")
    return any(url.startswith(proto) for proto in allowed)
"""
    mut_code_8 = """def is_safe_link(url: str) -> bool:
    allowed = ("http://", "https://", "mailto:")
    return all(url.startswith(proto) for proto in allowed)
"""
    oracle_8 = """def run_oracle():
    assert is_safe_link("https://example.com") is True, "HTTPS URL is safe"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Link Protocol Any vs All Check", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="BUILTIN_FUNCTION_REPLACEMENT", clean_code=clean_code_8, mutated_code=mut_code_8,
        test_code=oracle_8, expected_behavior="Allow if URL starts with ANY permitted protocol",
        observed_behavior="Requires URL to start with ALL protocols simultaneously", oracle_code=oracle_8
    ))
    idx += 1

    # 1.9 Draft version revision numbering increment
    clean_code_9 = """def increment_draft_version(major: int, minor: int) -> tuple:
    return major, minor + 1
"""
    mut_code_9 = """def increment_draft_version(major: int, minor: int) -> tuple:
    return major, minor - 1
"""
    oracle_9 = """def run_oracle():
    res = increment_draft_version(1, 4)
    assert res == (1, 5), f"Expected (1, 5), got {res}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Draft Minor Version Increment", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="ARITHMETIC_OPERATOR_REPLACEMENT", clean_code=clean_code_9, mutated_code=mut_code_9,
        test_code=oracle_9, expected_behavior="Increment minor revision",
        observed_behavior="Decrements minor revision", oracle_code=oracle_9
    ))
    idx += 1

    # 1.10 Table of contents anchor generator
    clean_code_10 = """def build_toc_anchor(heading: str) -> str:
    cleaned = heading.lower().replace(" ", "-")
    return f"#{cleaned}"
"""
    mut_code_10 = """def build_toc_anchor(heading: str) -> str:
    cleaned = heading.lower().replace(" ", "-")
    return f"{cleaned}"
"""
    oracle_10 = """def run_oracle():
    a = build_toc_anchor("Getting Started")
    assert a == "#getting-started", f"Expected #getting-started, got {a}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="TOC Anchor Hash Prefix", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="DROPPED_ANCHOR_PREFIX", clean_code=clean_code_10, mutated_code=mut_code_10,
        test_code=oracle_10, expected_behavior="Include # prefix in anchor URI",
        observed_behavior="Drops # prefix breaking HTML in-page jump links", oracle_code=oracle_10
    ))
    idx += 1

    # 1.11 Article publication status progression
    clean_code_11 = """def can_transition_status(current: str, target: str) -> bool:
    valid = {
        "DRAFT": {"REVIEW", "ARCHIVED"},
        "REVIEW": {"PUBLISHED", "DRAFT"},
        "PUBLISHED": {"ARCHIVED"}
    }
    return target in valid.get(current, set())
"""
    mut_code_11 = """def can_transition_status(current: str, target: str) -> bool:
    valid = {
        "DRAFT": {"REVIEW", "ARCHIVED"},
        "REVIEW": {"PUBLISHED", "DRAFT"},
        "PUBLISHED": {"ARCHIVED"}
    }
    return target not in valid.get(current, set())
"""
    oracle_11 = """def run_oracle():
    assert can_transition_status("DRAFT", "REVIEW") is True, "DRAFT -> REVIEW is valid"
    assert can_transition_status("DRAFT", "PUBLISHED") is False, "Direct DRAFT -> PUBLISHED forbidden"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Editorial Workflow State Transition", difficulty="medium",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=7,
        mutation_op="MEMBERSHIP_OPERATOR_INVERSION", clean_code=clean_code_11, mutated_code=mut_code_11,
        test_code=oracle_11, expected_behavior="Permit valid transitions",
        observed_behavior="Inverts workflow allowing invalid transitions", oracle_code=oracle_11
    ))
    idx += 1

    # 1.12 Estimated read progress percentage
    clean_code_12 = """def calculate_reading_progress(current_offset: int, total_length: int) -> int:
    if total_length <= 0:
        return 0
    ratio = min(1.0, current_offset / total_length)
    return int(ratio * 100)
"""
    mut_code_12 = """def calculate_reading_progress(current_offset: int, total_length: int) -> int:
    if total_length <= 0:
        return 0
    ratio = max(1.0, current_offset / total_length)
    return int(ratio * 100)
"""
    oracle_12 = """def run_oracle():
    pct = calculate_reading_progress(50, 100)
    assert pct == 50, f"Expected 50%, got {pct}%"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Reading Progress Ratio Clamp", difficulty="easy",
        category="functional_bug", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="MIN_MAX_INVERSION", clean_code=clean_code_12, mutated_code=mut_code_12,
        test_code=oracle_12, expected_behavior="Cap ratio at 1.0 using min()",
        observed_behavior="Uses max() fixing ratio at >= 100%", oracle_code=oracle_12
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 2. SECURITY VULNERABILITIES (6 scenarios)
    # -------------------------------------------------------------------------
    # 2.1 CWE-89 SQLi in article search query
    clean_sec_1 = """def search_articles_by_tag(db_cursor, tag: str):
    query = "SELECT id, title, slug FROM articles WHERE tag = ?"
    db_cursor.execute(query, (tag,))
    return db_cursor.fetchall()
"""
    mut_sec_1 = """def search_articles_by_tag(db_cursor, tag: str):
    query = f"SELECT id, title, slug FROM articles WHERE tag = '{tag}'"
    db_cursor.execute(query)
    return db_cursor.fetchall()
"""
    oracle_sec_1 = """class MockArticleCur:
    def __init__(self):
        self.params = None
    def execute(self, q, p=None):
        self.params = p
    def fetchall(self):
        return []

def run_oracle():
    cur = MockArticleCur()
    search_articles_by_tag(cur, "tech' OR 1=1--")
    assert cur.params is not None, "Article search query must be parameterized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Article Search Query SQL Injection", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-89", expected_line=2,
        mutation_op="SQL_STRING_INJECTION", clean_code=clean_sec_1, mutated_code=mut_sec_1,
        test_code=oracle_sec_1, expected_behavior="Parameterized tag search query",
        observed_behavior="String interpolation allows SQL injection", oracle_code=oracle_sec_1
    ))
    idx += 1

    # 2.2 CWE-78 Command injection in pandoc document conversion
    clean_sec_2 = """import subprocess
def convert_markdown_to_epub(input_file: str, output_file: str):
    if not input_file.replace(".", "").isalnum():
        raise ValueError("Invalid input filename")
    subprocess.run(["pandoc", input_file, "-o", output_file], check=True)
"""
    mut_sec_2 = """import subprocess
def convert_markdown_to_epub(input_file: str, output_file: str):
    subprocess.run(f"pandoc {input_file} -o {output_file}", shell=True, check=True)
"""
    oracle_sec_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(convert_markdown_to_epub)
    assert "shell=True" not in src, "Must avoid shell execution in document conversion"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Pandoc Document Subprocess Shell Injection", difficulty="hard",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-78", expected_line=3,
        mutation_op="SHELL_COMMAND_INTERPOLATION", clean_code=clean_sec_2, mutated_code=mut_sec_2,
        test_code=oracle_sec_2, expected_behavior="Subprocess list execution without shell",
        observed_behavior="Shell execution with unquoted filename parameter", oracle_code=oracle_sec_2
    ))
    idx += 1

    # 2.3 CWE-22 Path traversal in markdown asset loader
    clean_sec_3 = """import os
def load_markdown_asset(asset_filename: str) -> str:
    base = "/app/content/assets"
    clean = os.path.basename(asset_filename)
    return os.path.join(base, clean)
"""
    mut_sec_3 = """import os
def load_markdown_asset(asset_filename: str) -> str:
    base = "/app/content/assets"
    return os.path.join(base, asset_filename)
"""
    oracle_sec_3 = """def run_oracle():
    target = load_markdown_asset("../../config/secrets.json")
    assert "/secrets.json" not in target and ".." not in target, "Path traversal in asset loader"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Content Asset File Path Traversal", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-22", expected_line=4,
        mutation_op="UNSANITIZED_PATH_JOIN", clean_code=clean_sec_3, mutated_code=mut_sec_3,
        test_code=oracle_sec_3, expected_behavior="Sanitize asset path with basename",
        observed_behavior="Direct path join allows directory traversal", oracle_code=oracle_sec_3
    ))
    idx += 1

    # 2.4 CWE-79 XSS in markdown raw HTML rendering
    clean_sec_4 = """import html
def render_author_bio(bio_text: str) -> str:
    return f"<div class='bio'>{html.escape(bio_text)}</div>"
"""
    mut_sec_4 = """def render_author_bio(bio_text: str) -> str:
    return f"<div class='bio'>{bio_text}</div>"
"""
    oracle_sec_4 = """def run_oracle():
    res = render_author_bio("<script>stealCookies()</script>")
    assert "<script>" not in res and "&lt;script&gt;" in res, "HTML characters must be escaped"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Author Bio HTML Escaping", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-79", expected_line=2,
        mutation_op="MISSING_HTML_ESCAPING", clean_code=clean_sec_4, mutated_code=mut_sec_4,
        test_code=oracle_sec_4, expected_behavior="Escape HTML characters in author bio",
        observed_behavior="Unescaped bio reflection allows XSS", oracle_code=oracle_sec_4
    ))
    idx += 1

    # 2.5 CWE-306 Missing authentication on publish article action
    clean_sec_5 = """def publish_article_draft(article_id: str, author_token: str) -> bool:
    if not author_token:
        raise PermissionError("Unauthenticated publish action")
    return True
"""
    mut_sec_5 = """def publish_article_draft(article_id: str, author_token: str) -> bool:
    return True
"""
    oracle_sec_5 = """def run_oracle():
    try:
        publish_article_draft("ART-101", "")
        assert False, "Publishing without token must raise PermissionError"
    except PermissionError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Article Publication Authentication Guard", difficulty="medium",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-306", expected_line=2,
        mutation_op="AUTH_CHECK_REMOVAL", clean_code=clean_sec_5, mutated_code=mut_sec_5,
        test_code=oracle_sec_5, expected_behavior="Verify caller token before publishing",
        observed_behavior="Allows unauthenticated publishing", oracle_code=oracle_sec_5
    ))
    idx += 1

    # 2.6 CWE-862 Missing authorization for article deletion
    clean_sec_6 = """def delete_article(user_role: str, article_id: str) -> bool:
    return user_role in {"EDITOR_IN_CHIEF", "ADMIN"}
"""
    mut_sec_6 = """def delete_article(user_role: str, article_id: str) -> bool:
    return True
"""
    oracle_sec_6 = """def run_oracle():
    assert delete_article("CONTRIBUTOR", "ART-101") is False, "Contributor cannot delete articles"
    assert delete_article("EDITOR_IN_CHIEF", "ART-101") is True
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Article Deletion Role Authorization", difficulty="easy",
        category="security_vulnerability", has_defect=True, expected_cwe="CWE-862", expected_line=2,
        mutation_op="AUTHORIZATION_BYPASS", clean_code=clean_sec_6, mutated_code=mut_sec_6,
        test_code=oracle_sec_6, expected_behavior="Restrict deletion to authorized editorial roles",
        observed_behavior="Grants article deletion to any user role", oracle_code=oracle_sec_6
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 3. PERFORMANCE BOTTLENECKS (5 scenarios)
    # -------------------------------------------------------------------------
    # 3.1 Linear scan for prohibited keywords instead of set lookup
    clean_perf_1 = """def filter_banned_words(words: list, banned_set: set) -> list:
    return [w for w in words if w not in banned_set]
"""
    mut_perf_1 = """def filter_banned_words(words: list, banned_list: list) -> list:
    res = []
    for w in words:
        if w not in banned_list:
            res.append(w)
    return res
"""
    oracle_perf_1 = """def run_oracle():
    import inspect
    src = inspect.getsource(filter_banned_words)
    assert "set" in src, "Banned words filtering must use set for O(1) membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Banned Word Set Filtering", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="LINEAR_SEARCH_SUBSTITUTION", clean_code=clean_perf_1, mutated_code=mut_perf_1,
        test_code=oracle_perf_1, expected_behavior="Set-based keyword filtering in O(N)",
        observed_behavior="List scan in O(N*M)", oracle_code=oracle_perf_1
    ))
    idx += 1

    # 3.2 Quadratic tag association search
    clean_perf_2 = """def match_article_tags(article_tags: list, filter_tags: set) -> list:
    return [t for t in article_tags if t in filter_tags]
"""
    mut_perf_2 = """def match_article_tags(article_tags: list, filter_tags_list: list) -> list:
    res = []
    for t in article_tags:
        found = False
        for f in filter_tags_list:
            if t == f:
                found = True
                break
        if found:
            res.append(t)
    return res
"""
    oracle_perf_2 = """def run_oracle():
    import inspect
    src = inspect.getsource(match_article_tags)
    assert "set" in src, "Tag matching must use set membership"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tag Intersection Set Filtering", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=5,
        mutation_op="QUADRATIC_NESTED_FILTER", clean_code=clean_perf_2, mutated_code=mut_perf_2,
        test_code=oracle_perf_2, expected_behavior="Set intersection in linear time",
        observed_behavior="Nested loop list comparison", oracle_code=oracle_perf_2
    ))
    idx += 1

    # 3.3 Unmemoized recursive markdown nested list parsing
    clean_perf_3 = """def count_nested_list_items(node: dict, memo=None) -> int:
    if memo is None:
        memo = {}
    node_id = id(node)
    if node_id in memo:
        return memo[node_id]
    children = node.get("children", [])
    total = 1 + sum(count_nested_list_items(c, memo) for c in children)
    memo[node_id] = total
    return total
"""
    mut_perf_3 = """def count_nested_list_items(node: dict, memo=None) -> int:
    children = node.get("children", [])
    return 1 + sum(count_nested_list_items(c) for c in children)
"""
    oracle_perf_3 = """def run_oracle():
    import inspect
    src = inspect.getsource(count_nested_list_items)
    assert "memo" in src and "memo[" in src, "Nested tree traversal must be memoized"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Nested List Tree Traversal Memoization", difficulty="hard",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REMOVAL_OF_MEMOIZATION", clean_code=clean_perf_3, mutated_code=mut_perf_3,
        test_code=oracle_perf_3, expected_behavior="Memoized tree node counting",
        observed_behavior="Exponential re-traversal of shared subtrees", oracle_code=oracle_perf_3
    ))
    idx += 1

    # 3.4 Repeated string concatenation in HTML table of contents generator
    clean_perf_4 = """def build_html_toc(headings: list) -> str:
    parts = ["<nav class='toc'><ul>\\n"]
    for h in headings:
        parts.append(f"<li><a href='#{h['slug']}'>{h['title']}</a></li>\\n")
    parts.append("</ul></nav>")
    return "".join(parts)
"""
    mut_perf_4 = """def build_html_toc(headings: list) -> str:
    res = "<nav class='toc'><ul>\\n"
    for h in headings:
        res = res + f"<li><a href='#{h['slug']}'>{h['title']}</a></li>\\n"
    res = res + "</ul></nav>"
    return res
"""
    oracle_perf_4 = """def run_oracle():
    import inspect
    src = inspect.getsource(build_html_toc)
    assert ".join(" in src, "TOC generator must use list buffer join"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="TOC Buffer String Concatenation", difficulty="medium",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=4,
        mutation_op="QUADRATIC_STRING_CONCATENATION", clean_code=clean_perf_4, mutated_code=mut_perf_4,
        test_code=oracle_perf_4, expected_behavior="Join preallocated list buffer in O(N)",
        observed_behavior="Repeated string concatenation in loop", oracle_code=oracle_perf_4
    ))
    idx += 1

    # 3.5 Recompilation of slug validation regex
    clean_perf_5 = """import re
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
def is_valid_slug_format(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))
"""
    mut_perf_5 = """import re
def is_valid_slug_format(slug: str) -> bool:
    r = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    return bool(r.match(slug))
"""
    oracle_perf_5 = """def run_oracle():
    import inspect
    src = inspect.getsource(is_valid_slug_format)
    assert "re.compile" not in src, "Slug regex must be precompiled once at module level"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Slug Regex Precompilation", difficulty="easy",
        category="performance_bottleneck", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="REDUNDANT_REGEX_COMPILATION", clean_code=clean_perf_5, mutated_code=mut_perf_5,
        test_code=oracle_perf_5, expected_behavior="Precompiled module regex",
        observed_behavior="Recompiles pattern inside function", oracle_code=oracle_perf_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 4. REGRESSION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 4.1 Dropped empty title rejection
    clean_reg_1 = """def save_article_title(title: str) -> bool:
    cleaned = title.strip()
    if not cleaned:
        raise ValueError("Article title cannot be empty")
    return True
"""
    mut_reg_1 = """def save_article_title(title: str) -> bool:
    return True
"""
    oracle_reg_1 = """def run_oracle():
    try:
        save_article_title("   ")
        assert False, "Regression: Blank title must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Blank Title Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_1, mutated_code=mut_reg_1,
        test_code=oracle_reg_1, expected_behavior="Reject empty or whitespace-only article titles",
        observed_behavior="Accepts blank article titles", oracle_code=oracle_reg_1
    ))
    idx += 1

    # 4.2 Handling negative read time offset
    clean_reg_2 = """def format_reading_time_badge(mins: int) -> str:
    if mins < 1:
        raise ValueError("Reading time must be at least 1 min")
    return f"{mins} min read"
"""
    mut_reg_2 = """def format_reading_time_badge(mins: int) -> str:
    return f"{mins} min read"
"""
    oracle_reg_2 = """def run_oracle():
    try:
        format_reading_time_badge(-5)
        assert False, "Regression: Negative reading time must raise ValueError"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Negative Reading Time Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="GUARD_CLAUSE_REMOVAL", clean_code=clean_reg_2, mutated_code=mut_reg_2,
        test_code=oracle_reg_2, expected_behavior="Reject negative reading times",
        observed_behavior="Emits negative reading time badges", oracle_code=oracle_reg_2
    ))
    idx += 1

    # 4.3 Missing legacy slug prefix
    clean_reg_3 = """def format_canonical_slug(slug_body: str) -> str:
    return f"/posts/{slug_body.strip()}"
"""
    mut_reg_3 = """def format_canonical_slug(slug_body: str) -> str:
    return f"/{slug_body.strip()}"
"""
    oracle_reg_3 = """def run_oracle():
    s = format_canonical_slug("my-post")
    assert s == "/posts/my-post", f"Expected /posts/my-post, got {s}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Canonical Slug Prefix Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_CODE_PREFIX", clean_code=clean_reg_3, mutated_code=mut_reg_3,
        test_code=oracle_reg_3, expected_behavior="Include /posts/ prefix",
        observed_behavior="Drops /posts/ prefix breaking permalinks", oracle_code=oracle_reg_3
    ))
    idx += 1

    # 4.4 Lost whitespace trimming in tag names
    clean_reg_4 = """def normalize_article_tag(tag: str) -> str:
    cleaned = tag.strip().lower()
    if not cleaned:
        raise ValueError("Empty tag")
    return cleaned
"""
    mut_reg_4 = """def normalize_article_tag(tag: str) -> str:
    return tag.lower()
"""
    oracle_reg_4 = """def run_oracle():
    t = normalize_article_tag("  python  ")
    assert t == "python", f"Expected 'python' without spaces, got '{t}'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tag Whitespace Trimming Regression", difficulty="medium",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OMISSION_OF_STRIP", clean_code=clean_reg_4, mutated_code=mut_reg_4,
        test_code=oracle_reg_4, expected_behavior="Strip whitespace before normalizing tag",
        observed_behavior="Preserves leading/trailing spaces", oracle_code=oracle_reg_4
    ))
    idx += 1

    # 4.5 Dropped null safety guard on article excerpt summary
    clean_reg_5 = """def format_article_summary(summary: str) -> str:
    if summary is None:
        return ""
    return summary.strip()
"""
    mut_reg_5 = """def format_article_summary(summary: str) -> str:
    return summary.strip()
"""
    oracle_reg_5 = """def run_oracle():
    assert format_article_summary(None) == "", "None summary must return empty string"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Article Summary Null Guard Regression", difficulty="easy",
        category="regression", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="NULL_POINTER_DEREFERENCE", clean_code=clean_reg_5, mutated_code=mut_reg_5,
        test_code=oracle_reg_5, expected_behavior="Handle None summary gracefully",
        observed_behavior="Raises AttributeError on None summary", oracle_code=oracle_reg_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 5. INTEGRATION DEFECTS (5 scenarios)
    # -------------------------------------------------------------------------
    # 5.1 Renamed payload key in CMS publishing adapter
    clean_integ_1 = """def build_publish_event(article_id: str, title: str) -> dict:
    return {"article_identifier": article_id, "article_title": title, "status": "PUBLISHED"}
"""
    mut_integ_1 = """def build_publish_event(article_id: str, title: str) -> dict:
    return {"id": article_id, "name": title, "status": "PUBLISHED"}
"""
    oracle_integ_1 = """def run_oracle():
    p = build_publish_event("ART-1", "Intro to AI")
    assert "article_identifier" in p and "article_title" in p, "Consumer requires 'article_identifier' and 'article_title'"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="CMS Publishing Event Schema Keys", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="SCHEMA_KEY_MUTATION", clean_code=clean_integ_1, mutated_code=mut_integ_1,
        test_code=oracle_integ_1, expected_behavior="Contract specified schema keys",
        observed_behavior="Emits abbreviated keys breaking CMS downstream consumer", oracle_code=oracle_integ_1
    ))
    idx += 1

    # 5.2 Return type mismatch (dictionary vs list) in author metadata query
    clean_integ_2 = """def fetch_author_profile(author_id: str) -> dict:
    return {"author_id": author_id, "name": "Jane Doe"}
"""
    mut_integ_2 = """def fetch_author_profile(author_id: str) -> list:
    return [author_id, "Jane Doe"]
"""
    oracle_integ_2 = """def run_oracle():
    res = fetch_author_profile("AUT-1")
    assert isinstance(res, dict) and "name" in res, "Consumer expects author dictionary"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Author Profile Return Type Contract", difficulty="medium",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="RETURN_TYPE_ALTERATION", clean_code=clean_integ_2, mutated_code=mut_integ_2,
        test_code=oracle_integ_2, expected_behavior="Return dictionary conforming to REST client",
        observed_behavior="Returns plain list", oracle_code=oracle_integ_2
    ))
    idx += 1

    # 5.3 Missing authorization header in static site deployment webhook
    clean_integ_3 = """def build_deploy_webhook_headers(secret: str) -> dict:
    return {"X-Deploy-Token": secret, "Content-Type": "application/json", "User-Agent": "CMS-Dispatcher"}
"""
    mut_integ_3 = """def build_deploy_webhook_headers(secret: str) -> dict:
    return {"Content-Type": "application/json", "User-Agent": "CMS-Dispatcher"}
"""
    oracle_integ_3 = """def run_oracle():
    h = build_deploy_webhook_headers("deploy_secret_abc")
    assert "X-Deploy-Token" in h, "Deployment webhook receiver requires X-Deploy-Token header"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Deploy Webhook Token Header Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DROPPED_AUTH_HEADER", clean_code=clean_integ_3, mutated_code=mut_integ_3,
        test_code=oracle_integ_3, expected_behavior="Include X-Deploy-Token header",
        observed_behavior="Omits deployment security token header", oracle_code=oracle_integ_3
    ))
    idx += 1

    # 5.4 Date format string mismatch in RSS feed pubDate serializer
    clean_integ_4 = """def format_rss_pubdate(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"
"""
    mut_integ_4 = """def format_rss_pubdate(year: int, month: int, day: int) -> str:
    return f"{day:02d}/{month:02d}/{year:04d}"
"""
    oracle_integ_4 = """def run_oracle():
    d = format_rss_pubdate(2026, 7, 21)
    assert d == "2026-07-21", f"RSS serializer expects YYYY-MM-DD, got {d}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="RSS Publication Date Format", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="DATE_FORMAT_MISMATCH", clean_code=clean_integ_4, mutated_code=mut_integ_4,
        test_code=oracle_integ_4, expected_behavior="ISO 8601 date serialization",
        observed_behavior="Slash formatted date breaking feed reader", oracle_code=oracle_integ_4
    ))
    idx += 1

    # 5.5 Tag casing mismatch in taxonomy serializer
    clean_integ_5 = """def serialize_canonical_tag(tag: str) -> str:
    return tag.strip().upper()
"""
    mut_integ_5 = """def serialize_canonical_tag(tag: str) -> str:
    return tag.strip().lower()
"""
    oracle_integ_5 = """def run_oracle():
    assert serialize_canonical_tag("python") == "PYTHON", "Taxonomy standard requires uppercase canonical tags"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Taxonomy Tag Casing Contract", difficulty="easy",
        category="integration_defect", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="CASING_MUTATION", clean_code=clean_integ_5, mutated_code=mut_integ_5,
        test_code=oracle_integ_5, expected_behavior="Uppercase tag representation",
        observed_behavior="Emits lowercase tag", oracle_code=oracle_integ_5
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 6. SEMANTIC DRIFT (4 scenarios)
    # -------------------------------------------------------------------------
    # 6.1 Weakened editorial check: omitting plagiarism check assertion
    clean_drift_1 = """def verify_article_editorial_checks(checks: dict) -> bool:
    return checks.get("spellcheck_passed", False) and checks.get("originality_passed", False)
"""
    mut_drift_1 = """def verify_article_editorial_checks(checks: dict) -> bool:
    # Drift: loosened requirement to only check spelling
    return checks.get("spellcheck_passed", False)
"""
    oracle_drift_1 = """def run_oracle():
    checks = {"spellcheck_passed": True, "originality_passed": False}
    assert verify_article_editorial_checks(checks) is False, "Drift: Failed originality must reject article"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Originality Check Semantic Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="SPECIFICATION_ASSERTION_WEAKENING", clean_code=clean_drift_1, mutated_code=mut_drift_1,
        test_code=oracle_drift_1, expected_behavior="Enforce both spellcheck and originality",
        observed_behavior="Loosens check allowing unoriginal content to pass", oracle_code=oracle_drift_1
    ))
    idx += 1

    # 6.2 Silent behavior divergence: dropping draft status validation on publish
    clean_drift_2 = """def process_publish_transition(doc: dict) -> dict:
    if doc.get("status") != "REVIEW":
        raise ValueError("Only reviewed drafts can be published")
    return {"id": doc.get("id"), "status": "PUBLISHED"}
"""
    mut_drift_2 = """def process_publish_transition(doc: dict) -> dict:
    # Drift: status precondition silently dropped
    return {"id": doc.get("id"), "status": "PUBLISHED"}
"""
    oracle_drift_2 = """def run_oracle():
    try:
        process_publish_transition({"id": "1", "status": "DRAFT"})
        assert False, "Drift: Unreviewed DRAFT cannot transition directly to PUBLISHED"
    except ValueError:
        pass
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Editorial State Transition Precondition Drift", difficulty="medium",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CONTRACT_REQUIREMENT_DROPPED", clean_code=clean_drift_2, mutated_code=mut_drift_2,
        test_code=oracle_drift_2, expected_behavior="Require REVIEW status before publishing",
        observed_behavior="Silently drops precondition allowing raw drafts to publish", oracle_code=oracle_drift_2
    ))
    idx += 1

    # 6.3 Maximum title character limit invariant removal
    clean_drift_3 = """def validate_title_length(title: str, max_chars: int = 120) -> bool:
    if len(title) > max_chars:
        return False
    return True
"""
    mut_drift_3 = """def validate_title_length(title: str, max_chars: int = 120) -> bool:
    # Drift: title length limit removed
    return True
"""
    oracle_drift_3 = """def run_oracle():
    assert validate_title_length("A" * 200, 120) is False, "Drift: 200-char title exceeds 120-char max"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Title Character Limit Invariant Drift", difficulty="easy",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="INVARIANT_REMOVAL", clean_code=clean_drift_3, mutated_code=mut_drift_3,
        test_code=oracle_drift_3, expected_behavior="Enforce title length limit",
        observed_behavior="Unconditionally permits unbounded title lengths", oracle_code=oracle_drift_3
    ))
    idx += 1

    # 6.4 Rounding drift in reading percentage calculation
    clean_drift_4 = """def compute_scroll_pct(current: int, total: int) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    dec = (Decimal(str(current)) / Decimal(str(total))) * Decimal("100")
    return float(dec.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
"""
    mut_drift_4 = """def compute_scroll_pct(current: int, total: int) -> float:
    # Drift: integer truncation of intermediate percentage
    return float(int(current * 100 / total))
"""
    oracle_drift_4 = """def run_oracle():
    res = compute_scroll_pct(33, 100)
    assert res == 33.0, f"Expected 33.0, got {res}"
    res2 = compute_scroll_pct(1, 3)
    assert res2 == 33.3, f"Expected 33.3 after half-up, got {res2}"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Scroll Percentage Decimal Rounding Drift", difficulty="hard",
        category="semantic_drift", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="ROUNDING_PRECISION_TRUNCATION", clean_code=clean_drift_4, mutated_code=mut_drift_4,
        test_code=oracle_drift_4, expected_behavior="Accurate 1-decimal percentage rounding",
        observed_behavior="Integer truncation drops decimal fraction", oracle_code=oracle_drift_4
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 7. NON-CONVERGENT REPAIR (3 scenarios)
    # -------------------------------------------------------------------------
    # 7.1 Conflicting article length guidelines
    clean_conv_1 = """def check_content_length_guidelines(words: int) -> bool:
    # Harmonized editorial guideline: acceptable between 500 and 2000 words
    return 500 <= words <= 2000
"""
    mut_conv_1 = """def check_content_length_guidelines(words: int) -> bool:
    # Invariant conflict: Guideline A requires words < 400, Guideline B requires words > 800
    return words < 400 and words > 800
"""
    oracle_conv_1 = """def run_oracle():
    assert check_content_length_guidelines(1000) is True, "Harmonized rule permits 1000 words"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Content Length Policy Cyclic Constraint", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="MUTUALLY_EXCLUSIVE_REQUIREMENTS", clean_code=clean_conv_1, mutated_code=mut_conv_1,
        test_code=oracle_conv_1, expected_behavior="Valid word count range",
        observed_behavior="Mutually contradictory rules (words < 400 AND words > 800)",
        oracle_code=oracle_conv_1, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.2 Oscillating patch repair: tag count threshold operator
    clean_conv_2 = """def evaluate_tag_quota(count: int, quota: int) -> str:
    if count >= quota:
        return "QUOTA_MET"
    return "NEEDS_MORE"
"""
    mut_conv_2 = """def evaluate_tag_quota(count: int, quota: int) -> str:
    if count > quota:
        return "QUOTA_MET"
    return "NEEDS_MORE"
"""
    oracle_conv_2 = """def run_oracle():
    assert evaluate_tag_quota(3, 3) == "QUOTA_MET", "Exact quota must be QUOTA_MET"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Tag Quota Boundary Oscillation", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=2,
        mutation_op="OSCILLATING_BOUNDARY_OPERATOR", clean_code=clean_conv_2, mutated_code=mut_conv_2,
        test_code=oracle_conv_2, expected_behavior="Exact boundary meets quota",
        observed_behavior="Oscillates between strictly greater and greater-equal",
        oracle_code=oracle_conv_2, is_repair_loop_scenario=True
    ))
    idx += 1

    # 7.3 Circular state transition in article editorial review
    clean_conv_3 = """def advance_editorial_review(status: str) -> str:
    flow = {"SUBMITTED": "ASSIGNED", "ASSIGNED": "EDITING", "EDITING": "APPROVED", "APPROVED": "APPROVED"}
    return flow.get(status, "SUBMITTED")
"""
    mut_conv_3 = """def advance_editorial_review(status: str) -> str:
    # Circular loop between EDITING and ASSIGNED
    flow = {"SUBMITTED": "ASSIGNED", "ASSIGNED": "EDITING", "EDITING": "ASSIGNED", "APPROVED": "APPROVED"}
    return flow.get(status, "SUBMITTED")
"""
    oracle_conv_3 = """def run_oracle():
    res = advance_editorial_review(advance_editorial_review("ASSIGNED"))
    assert res == "APPROVED", "Editorial review must reach terminal APPROVED state"
"""
    scenarios.append(ScenarioSpec(
        scenario_index=idx, name="Editorial Review State Machine Cycle", difficulty="hard",
        category="non_convergent_by_design", has_defect=True, expected_cwe=None, expected_line=3,
        mutation_op="CYCLIC_STATE_TRANSITION", clean_code=clean_conv_3, mutated_code=mut_conv_3,
        test_code=oracle_conv_3, expected_behavior="Linear state progression to APPROVED",
        observed_behavior="Infinite oscillation between ASSIGNED and EDITING",
        oracle_code=oracle_conv_3, is_repair_loop_scenario=True
    ))
    idx += 1

    # -------------------------------------------------------------------------
    # 8. CLEAN CONTROLS (10 scenarios)
    # -------------------------------------------------------------------------
    for c_idx in range(1, 11):
        clean_code_c = f"""def content_clean_routine_{c_idx}(word_count: int) -> int:
    # Clean control {c_idx}: verified article content calculation with boundary guard
    if word_count < 0:
        return 0
    return (word_count * 2) + {c_idx}
"""
        oracle_c = f"""def run_oracle():
    res = content_clean_routine_{c_idx}(50)
    assert res == 100 + {c_idx}, f"Expected {{100 + {c_idx}}}, got {{res}}"
    assert content_clean_routine_{c_idx}(-10) == 0, "Negative inputs clamped to 0"
"""
        scenarios.append(ScenarioSpec(
            scenario_index=idx, name=f"Content Clean Control {c_idx:02d}", difficulty="easy" if c_idx <= 5 else "medium",
            category="clean_control", has_defect=False, expected_cwe=None, expected_line=None,
            mutation_op=None, clean_code=clean_code_c, mutated_code=clean_code_c,
            test_code=oracle_c, expected_behavior=f"Correctly execute verified content calculation {c_idx}",
            observed_behavior="Clean execution without defects", oracle_code=oracle_c
        ))
        idx += 1

    return scenarios
