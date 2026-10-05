#!/usr/bin/env python3
"""Assignment 1: Implementing Myers' diff.

Commands:
    main.py lines A B       Part A: minimal line diff of file A to file B
    main.py highlight A B    Part B: the same diff, plus changed-character ranges

Only the Python standard library is used. The diff core (myers_diff) works on
any sequence and is reused for both the line diff (Part A) and the per-line
character diff (Part B).
"""

import sys


# ---------------------------------------------------------------------------
# Myers O(ND) difference algorithm
# ---------------------------------------------------------------------------
#
# Returns an edit script as a list of operations in forward (A, B) order:
#   ("keep",   i)        line a[i] is kept (also equals some b[j])
#   ("delete", i)        line a[i] is deleted
#   ("insert", j)        line b[j] is inserted
#
# The script is produced from Myers' backtracking so it is a *minimal* edit
# script (fewest deletions + insertions). Equality is tested on the sequence
# elements, so callers may pass sequences of hashed ints for speed.


def myers_diff(a, b):
    n = len(a)
    m = len(b)

    # Trim the common prefix and suffix first. This does not change
    # minimality and greatly shrinks the problem for typical inputs.
    prefix = 0
    while prefix < n and prefix < m and a[prefix] == b[prefix]:
        prefix += 1

    suffix = 0
    while (
        suffix < (n - prefix)
        and suffix < (m - prefix)
        and a[n - 1 - suffix] == b[m - 1 - suffix]
    ):
        suffix += 1

    script = []
    for i in range(prefix):
        script.append(("keep", i))

    middle = _myers_middle(a, b, prefix, n - suffix, prefix, m - suffix)
    script.extend(middle)

    for k in range(suffix):
        i = n - suffix + k
        script.append(("keep", i))

    return script


def _myers_middle(a, b, a_lo, a_hi, b_lo, b_hi):
    """Diff a[a_lo:a_hi] against b[b_lo:b_hi], returning ops with absolute
    indices into a and b. Implements the forward O(ND) search recording the
    V arrays, then backtracks to recover the edit script."""
    n = a_hi - a_lo
    m = b_hi - b_lo

    if n == 0 and m == 0:
        return []
    if n == 0:
        return [("insert", b_lo + j) for j in range(m)]
    if m == 0:
        return [("delete", a_lo + i) for i in range(n)]

    max_d = n + m

    # V is a dict keyed by diagonal k (k = x - y). Using a dict keeps memory
    # proportional to the number of diagonals actually visited (O(D)) instead
    # of O(N+M). For a small edit distance D this is the whole point: the
    # work and memory become O(D^2), not O(D*(N+M)).
    v = {1: 0}

    trace = []  # snapshot of only the touched diagonals after each d
    found_d = -1

    for d in range(max_d + 1):
        # Record just the active window [-d, d]; copying the whole V on every
        # d would be O(D*(N+M)) and is the warned-against quadratic blow-up.
        trace.append(dict(v))
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v.get(k - 1, -1) < v.get(k + 1, -1)):
                x = v.get(k + 1, 0)   # move down (insertion)
            else:
                x = v.get(k - 1, 0) + 1   # move right (deletion)
            y = x - k
            # Follow the diagonal snake of matching elements.
            while x < n and y < m and a[a_lo + x] == b[b_lo + y]:
                x += 1
                y += 1
            v[k] = x
            if x >= n and y >= m:
                found_d = d
                break
        if found_d != -1:
            break

    return _backtrack(a_lo, b_lo, n, m, trace, found_d)


def _backtrack(a_lo, b_lo, n, m, trace, d):
    """Walk the recorded V arrays backwards to build the edit script."""
    ops = []  # collected in reverse order
    x = n
    y = m
    for dd in range(d, 0, -1):
        v = trace[dd]
        k = x - y
        if k == -dd or (k != dd and v.get(k - 1, -1) < v.get(k + 1, -1)):
            prev_k = k + 1          # came from an insertion
        else:
            prev_k = k - 1          # came from a deletion
        prev_x = v[prev_k]
        prev_y = prev_x - prev_k

        # Snake (diagonal matches) between (prev move) and (x, y).
        while x > prev_x and y > prev_y:
            x -= 1
            y -= 1
            ops.append(("keep", a_lo + x))

        if dd > 0:
            if x == prev_x:
                # moved down -> insertion of b[prev_y]
                y -= 1
                ops.append(("insert", b_lo + y))
            else:
                # moved right -> deletion of a[prev_x]
                x -= 1
                ops.append(("delete", a_lo + x))

    # Remaining initial snake at d == 0.
    while x > 0 and y > 0:
        x -= 1
        y -= 1
        ops.append(("keep", a_lo + x))

    ops.reverse()
    return ops


# ---------------------------------------------------------------------------
# File reading (raw bytes, split on \n, drop a single trailing empty piece)
# ---------------------------------------------------------------------------


def read_lines(path):
    with open(path, "rb") as f:
        data = f.read()
    if data == b"":
        return []
    pieces = data.split(b"\n")
    if pieces and pieces[-1] == b"":
        pieces.pop()
    return pieces


# ---------------------------------------------------------------------------
# Change-block ordering: deletions before insertions.
#
# myers_diff already returns deletes before inserts within a run because the
# backtracking visits deletions (right moves) and insertions (down moves) in a
# fixed order. To be robust and explicit, we regroup each change block so that
# all deletes come before all inserts.
# ---------------------------------------------------------------------------


def ordered_blocks(script):
    """Yield output records as (kind, a_index_or_None, b_index_or_None),
    enforcing the delete-first rule within every change block."""
    out = []
    i = 0
    n = len(script)
    while i < n:
        kind = script[i][0]
        if kind == "keep":
            out.append(("keep", script[i][1], None))
            i += 1
            continue
        # Collect a maximal run of delete/insert (a change block).
        dels = []
        inss = []
        while i < n and script[i][0] != "keep":
            if script[i][0] == "delete":
                dels.append(script[i][1])
            else:
                inss.append(script[i][1])
            i += 1
        for a_idx in dels:
            out.append(("delete", a_idx, None))
        for b_idx in inss:
            out.append(("insert", None, b_idx))
    return out


# ---------------------------------------------------------------------------
# Part A: lines
# ---------------------------------------------------------------------------


def cmd_lines(a_path, b_path):
    a = read_lines(a_path)
    b = read_lines(b_path)
    script = diff_lines(a, b)
    records = ordered_blocks(script)

    out = sys.stdout.buffer
    for kind, ai, bj in records:
        if kind == "keep":
            out.write(b" ")
            out.write(a[ai])
        elif kind == "delete":
            out.write(b"-")
            out.write(a[ai])
        else:  # insert
            out.write(b"+")
            out.write(b[bj])
        out.write(b"\n")


def diff_lines(a, b):
    """Line diff. Hash each distinct line to a small int so the inner equality
    tests in Myers compare ints rather than whole byte strings."""
    pool = {}
    ca = _encode(a, pool)
    cb = _encode(b, pool)
    return myers_diff(ca, cb)


def _encode(lines, pool):
    out = []
    append = out.append
    for ln in lines:
        token = pool.get(ln)
        if token is None:
            token = len(pool)
            pool[ln] = token
        append(token)
    return out


# ---------------------------------------------------------------------------
# Part B: highlight
# ---------------------------------------------------------------------------


def cmd_highlight(a_path, b_path):
    a = read_lines(a_path)
    b = read_lines(b_path)
    script = diff_lines(a, b)
    records = ordered_blocks(script)

    out = sys.stdout.buffer

    # Walk records, and within each change block pair the k-th delete with the
    # k-th insert, emitting a "? ..." line after each paired insert line.
    i = 0
    n = len(records)
    while i < n:
        kind = records[i][0]
        if kind == "keep":
            out.write(b" ")
            out.write(a[records[i][1]])
            out.write(b"\n")
            i += 1
            continue

        # Gather the change block (contiguous deletes then inserts).
        del_idx = []
        ins_idx = []
        while i < n and records[i][0] != "keep":
            if records[i][0] == "delete":
                del_idx.append(records[i][1])
            else:
                ins_idx.append(records[i][2])
            i += 1

        # Emit all delete lines.
        for ai in del_idx:
            out.write(b"-")
            out.write(a[ai])
            out.write(b"\n")

        # Emit each insert line, with a ? range line after paired inserts.
        pairs = min(len(del_idx), len(ins_idx))
        for pos, bj in enumerate(ins_idx):
            out.write(b"+")
            out.write(b[bj])
            out.write(b"\n")
            if pos < pairs:
                old_line = a[del_idx[pos]]
                new_line = b[bj]
                range_line = char_ranges(old_line, new_line)
                out.write(range_line)
                out.write(b"\n")


def char_ranges(old_bytes, new_bytes):
    """Return the '? <old ranges> | <new ranges>' line (as bytes) describing
    the changed character ranges between two lines. Characters are Unicode
    code points. Highlight tests are always valid UTF-8."""
    old_cp = list(old_bytes.decode("utf-8"))
    new_cp = list(new_bytes.decode("utf-8"))

    script = myers_diff(old_cp, new_cp)

    # Changed positions: deletes mark positions in old, inserts in new.
    old_marks = []
    new_marks = []
    for op in script:
        if op[0] == "delete":
            old_marks.append(op[1])
        elif op[0] == "insert":
            new_marks.append(op[1])

    old_r = _ranges_to_str(old_marks)
    new_r = _ranges_to_str(new_marks)
    return b"? " + old_r + b" | " + new_r


def _ranges_to_str(marks):
    """Turn a sorted list of changed indices into merged 'start-end' ranges
    (end exclusive), comma separated, or '.' if empty."""
    if not marks:
        return b"."
    parts = []
    start = marks[0]
    prev = marks[0]
    for pos in marks[1:]:
        if pos == prev + 1:
            prev = pos
        else:
            parts.append(b"%d-%d" % (start, prev + 1))
            start = pos
            prev = pos
    parts.append(b"%d-%d" % (start, prev + 1))
    return b",".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv):
    if len(argv) != 4 or argv[1] not in ("lines", "highlight"):
        sys.stderr.write("usage: main.py {lines|highlight} A B\n")
        return 2

    command = argv[1]
    a_path = argv[2]
    b_path = argv[3]

    # If either file cannot be read: print nothing on stdout, exit code 2.
    try:
        if command == "lines":
            cmd_lines(a_path, b_path)
        else:
            cmd_highlight(a_path, b_path)
    except OSError as e:
        sys.stderr.write("error: cannot read input file: %s\n" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
