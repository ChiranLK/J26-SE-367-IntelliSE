"""STEP 2 - Convert GenMyModel UML2 XMI into clean PlantUML text.

Input : data/manifest.csv (from step 1)
Output: data/puml/<safe_id>.puml  +  data/converted.csv

Class models   -> classes / interfaces / enums, attributes, operations,
                  generalization, realization, associations (with multiplicity,
                  aggregation/composition) and dependencies.
Use-case models-> actors, use cases (grouped in a 'rectangle' when they belong
                  to a subject/package), actor-usecase associations, include,
                  extend and generalization.

The converter is deliberately conservative: anything it cannot map reliably is
skipped, because these files become the *clean positive* examples.

Usage: python step2_xmi_to_plantuml.py --manifest data/manifest.csv --out data/puml
"""
import argparse
import csv
import re
from pathlib import Path

from lxml import etree

VIS = {"public": "+", "private": "-", "protected": "#", "package": "~"}


# ----------------------------------------------------------------- helpers
def local(tag):
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def xtype(el):
    """uml:Class etc. from xsi:type or xmi:type (GenMyModel files use both).
    Some containment tags imply the type and carry no xsi:type (e.g. ownedUseCase)."""
    for k, v in el.attrib.items():
        if local(k) == "type" and ("XMLSchema-instance" in k or "XMI" in k or "omg.org" in k):
            return v.split(":")[-1]
    return {"ownedUseCase": "UseCase", "ownedLiteral": "EnumerationLiteral"}.get(local(el.tag))


def xid(el):
    for k, v in el.attrib.items():
        if local(k) == "id":
            return v
    return None


def ident(name, fallback="X"):
    """Safe PlantUML identifier (letters, digits, underscore)."""
    s = re.sub(r"[^0-9A-Za-z_]+", "_", (name or "").strip()).strip("_")
    if not s:
        s = fallback
    if s[0].isdigit():
        s = "_" + s
    return s


def clean_label(text):
    return re.sub(r'["{}\n\r]', " ", (text or "")).strip()


def type_name(el, by_id):
    """Resolve a type given as attribute (id) or as child <type href="...#String"/>."""
    t = el.get("type")
    if t and t in by_id:
        return by_id[t].get("name")
    for c in el:
        if local(c.tag) == "type":
            href = c.get("href", "")
            if "#" in href:
                return href.split("#")[-1]
            ref = c.get("{http://www.omg.org/XMI}idref") or c.get("idref")
            if ref in by_id:
                return by_id[ref].get("name")
    return None


def mult_bound(el, which):
    for c in el:
        if local(c.tag) == which:
            return c.get("value", "0" if which == "lowerValue" else "1")
    return None


def multiplicity(end):
    lo, up = mult_bound(end, "lowerValue"), mult_bound(end, "upperValue")
    if lo is None and up is None:
        return None
    lo = lo if lo is not None else "1"
    up = up if up is not None else "1"
    if up == "-1":
        up = "*"
    return lo if lo == up else f"{lo}..{up}"


# ----------------------------------------------------------------- class diagrams
def convert_class_model(root):
    by_id = {xid(e): e for e in root.iter() if xid(e)}
    classifiers = [e for e in root.iter() if xtype(e) in ("Class", "Interface", "Enumeration") and e.get("name")]
    if not classifiers:
        return None
    names = {}
    for e in classifiers:
        base, n = ident(e.get("name")), 2
        cand = base
        while cand in names.values():
            cand, n = f"{base}{n}", n + 1
        names[xid(e)] = cand

    out = ["@startuml"]
    for e in classifiers:
        kind = {"Class": "abstract class" if e.get("isAbstract") == "true" else "class",
                "Interface": "interface", "Enumeration": "enum"}[xtype(e)]
        body = []
        for c in e:
            tag = local(c.tag)
            if tag == "ownedAttribute" and not c.get("association") and c.get("name"):
                vis = VIS.get(c.get("visibility", ""), "")
                t = type_name(c, by_id)
                body.append(f"{vis}{ident(c.get('name'))}" + (f" : {ident(t)}" if t else ""))
            elif tag == "ownedOperation" and c.get("name"):
                vis = VIS.get(c.get("visibility", ""), "")
                params, ret = [], None
                for p in c:
                    if local(p.tag) != "ownedParameter":
                        continue
                    pt = type_name(p, by_id)
                    if p.get("direction") == "return":
                        ret = pt
                    elif p.get("name"):
                        params.append(ident(p.get("name")) + (f" : {ident(pt)}" if pt else ""))
                body.append(f"{vis}{ident(c.get('name'))}({', '.join(params)})" + (f" : {ident(ret)}" if ret else ""))
            elif tag == "ownedLiteral" and c.get("name"):
                body.append(ident(c.get("name")))
        if body:
            out.append(f"{kind} {names[xid(e)]} {{")
            out += [f"  {b}" for b in body]
            out.append("}")
        else:
            out.append(f"{kind} {names[xid(e)]}")

    rel = []
    for e in classifiers:
        for c in e:
            tag = local(c.tag)
            if tag == "generalization" and c.get("general") in names:
                rel.append(f"{names[c.get('general')]} <|-- {names[xid(e)]}")
            elif tag == "interfaceRealization" and c.get("contract") in names:
                rel.append(f"{names[c.get('contract')]} <|.. {names[xid(e)]}")

    for a in (e for e in root.iter() if xtype(e) == "Association"):
        ends = [by_id.get(m) for m in (a.get("memberEnd") or "").split()]
        ends = [x for x in ends if x is not None]
        if len(ends) != 2:
            ends = [c for c in a if local(c.tag) == "ownedEnd"][:2]
        if len(ends) != 2:
            continue
        t0, t1 = ends[0].get("type"), ends[1].get("type")
        if t0 not in names or t1 not in names:
            continue
        # A multiplicity is written next to the class that types that end.
        # In UML2 the end marked aggregation=composite|shared is typed by the PART,
        # so the other end is the WHOLE:  Whole *-- Part
        agg_end = next((x for x in ends if x.get("aggregation") in ("composite", "shared")), None)
        if agg_end is not None:
            whole = ends[1] if agg_end is ends[0] else ends[0]
            arrow = "*--" if agg_end.get("aggregation") == "composite" else "o--"
            first, second = whole, agg_end
        else:
            arrow, first, second = "--", ends[0], ends[1]
        lm, rm = multiplicity(first), multiplicity(second)
        src, dst = names[first.get("type")], names[second.get("type")]
        line = src + (f' "{lm}"' if lm else "") + f" {arrow} " + (f'"{rm}" ' if rm else "") + dst
        if a.get("name"):
            line += f" : {clean_label(a.get('name'))}"
        rel.append(line)

    for d in (e for e in root.iter() if xtype(e) in ("Dependency", "Usage")):
        cl, sp = d.get("client"), d.get("supplier")
        if cl in names and sp in names:
            rel.append(f"{names[cl]} ..> {names[sp]}")

    out += sorted(set(rel), key=rel.index)
    out.append("@enduml")
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- use case diagrams
def convert_usecase_model(root):
    by_id = {xid(e): e for e in root.iter() if xid(e)}
    actors = [e for e in root.iter() if xtype(e) == "Actor" and e.get("name")]
    ucs = [e for e in root.iter() if xtype(e) == "UseCase" and e.get("name")]
    if not ucs:
        return None
    names = {}
    for e in actors:
        names[xid(e)] = ident(e.get("name"), "Actor")
    for i, e in enumerate(ucs, 1):
        names[xid(e)] = f"UC{i}"
    # de-duplicate actor ids
    seen = {}
    for k, v in list(names.items()):
        if v in seen:
            names[k] = f"{v}_{sum(1 for x in names.values() if x.startswith(v))}"
        seen[names[k]] = k

    out = ["@startuml", "left to right direction"]
    for e in actors:
        n = e.get("name").strip()
        out.append(f'actor "{clean_label(n)}" as {names[xid(e)]}' if ident(n) != n else f"actor {names[xid(e)]}")

    # group use cases by their container subject (Component / Class / Package)
    groups = {}
    for e in ucs:
        parent = e.getparent()
        key = parent if parent is not None and xtype(parent) in ("Component", "Class", "Package") and parent.get("name") else None
        groups.setdefault(key, []).append(e)
    for parent, members in groups.items():
        indent = ""
        if parent is not None:
            out.append(f'rectangle "{clean_label(parent.get("name"))}" {{')
            indent = "  "
        for e in members:
            out.append(f'{indent}usecase "{clean_label(e.get("name"))}" as {names[xid(e)]}')
        if parent is not None:
            out.append("}")

    rel = []
    for a in (e for e in root.iter() if xtype(e) == "Association"):
        ends = [by_id.get(m) for m in (a.get("memberEnd") or "").split()]
        ends = [x for x in ends if x is not None]
        if len(ends) != 2:
            ends = [c for c in a if local(c.tag) == "ownedEnd"][:2]
        types = [x.get("type") for x in ends]
        if len(types) == 2 and all(t in names for t in types):
            act = [t for t in types if by_id.get(t) is not None and xtype(by_id[t]) == "Actor"]
            other = [t for t in types if t not in act]
            if act and other:
                rel.append(f"{names[act[0]]} --> {names[other[0]]}")
            else:
                rel.append(f"{names[types[0]]} -- {names[types[1]]}")
    for e in ucs + actors:
        for c in e:
            tag = local(c.tag)
            if tag == "include" and c.get("addition") in names:
                rel.append(f"{names[xid(e)]} ..> {names[c.get('addition')]} : <<include>>")
            elif tag == "extend" and c.get("extendedCase") in names:
                rel.append(f"{names[xid(e)]} ..> {names[c.get('extendedCase')]} : <<extend>>")
            elif tag == "generalization" and c.get("general") in names:
                rel.append(f"{names[c.get('general')]} <|-- {names[xid(e)]}")
    out += list(dict.fromkeys(rel))
    out.append("@enduml")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/manifest.csv")
    ap.add_argument("--out", default="data/puml")
    ap.add_argument("--csv_out", default="data/converted.csv")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    rows, fails = [], 0
    parser = etree.XMLParser(recover=True, huge_tree=True)
    for r in csv.DictReader(open(a.manifest, encoding="utf-8")):
        try:
            root = etree.parse(r["xmi_path"], parser).getroot()
            conv = convert_class_model if r["diagram_type"] == "CLASS" else convert_usecase_model
            puml = conv(root)
        except Exception as ex:  # corrupted XMI
            puml, fails = None, fails + 1
        if not puml:
            continue
        sid = ident(Path(r["id"]).stem)
        p = Path(a.out) / f"{sid}.puml"
        p.write_text(puml, encoding="utf-8")
        rows.append({**r, "puml_path": str(p)})
    with open(a.csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"converted {len(rows)} models (parse failures: {fails}) -> {a.csv_out}")


if __name__ == "__main__":
    main()
