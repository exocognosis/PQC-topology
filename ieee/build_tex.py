#!/usr/bin/env python3
"""Convert topological-pqc-discovery.html into an IEEEtran conference paper.

  python3 ieee/build_tex.py && (cd ieee && tectonic paper.tex)

Sections, tables, theorem-like blocks, math, the figure (redrawn in TikZ) and the
Appendix A listing are converted; author-year citations become numbered \\cite
in order of first citation; "§", "Table" and "Figure" references become \\ref.
The editor's note (Appendix C of the HTML) is omitted, so Appendix D becomes C.
"""
import os
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "topological-pqc-discovery.html")
OUT = os.path.join(HERE, "paper.tex")

UNI = {"→": r"$\rightarrow$", "←": r"$\leftarrow$", "↔": r"$\leftrightarrow$", "≤": r"$\le$", "≥": r"$\ge$",
       "×": r"$\times$", "′": r"$'$", "⊤": r"$\top$", "∞": r"$\infty$", "∎": r"\hfill$\blacksquare$",
       "≈": r"$\approx$", "∈": r"$\in$", "∉": r"$\notin$", "⊆": r"$\subseteq$", "∩": r"$\cap$", "∪": r"$\cup$",
       "ℝ": r"$\mathbb{R}$", "≠": r"$\ne$", "⁺": r"$^{+}$", "⁻": r"$^{-}$", "·": r"$\cdot$", "…": r"\ldots{}",
       "−": r"$-$", "σ": r"$\sigma$", "τ": r"$\tau$", "λ": r"$\lambda$", "Λ": r"$\Lambda$", "ω": r"$\omega$",
       "κ": r"$\kappa$", "π": r"$\pi$", "Σ": r"$\Sigma$", "μ": r"$\mu$", "≥": r"$\ge$", "₁": r"$_1$",
       "₂": r"$_2$", "₃": r"$_3$", "✓": r"\checkmark{}", "⟶": r"$\longrightarrow$", "⊥": r"$\bot$"}
SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
MATH_RE = re.compile(r"(\\\(.*?\\\)|\\\[.*?\\\])", re.S)


def esc_text(t):
    out = []
    for ch in t:
        out.append(SPECIAL.get(ch) or UNI.get(ch) or ch)
    return "".join(out)


def conv_text(t):
    parts = MATH_RE.split(t)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            if p.startswith("\\("):
                out.append("$" + p[2:-2].strip() + "$")
            else:
                out.append("\n" + display(p[2:-2].strip()) + "\n")
        else:
            out.append(esc_text(p))
    return "".join(out)


def display(m):
    """Display math sized for a single IEEE column."""
    if "\\qquad" in m:
        parts = [x.strip().rstrip(",") for x in m.split("\\qquad")]
        return "\\begin{gather*}\n" + " \\\\\n".join(parts) + "\n\\end{gather*}"
    if len(m) > 95 and ",\\;\\;" in m:
        a, b = m.split(",\\;\\;", 1)
        return "\\begin{multline*}\n" + a + ", \\\\\n" + b + "\n\\end{multline*}"
    return "\\[ " + m + " \\]"


def code(t):
    t = esc_text(t)
    return r"\texttt{" + t.replace(r"\_", r"\_\allowbreak{}") + "}"


def inline(node):
    """Inline content of a node as LaTeX."""
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            out.append(conv_text(str(c)))
            continue
        if not isinstance(c, Tag):
            continue
        cls = c.get("class") or []
        if c.name in ("strong", "b"):
            out.append(r"\textbf{" + inline(c) + "}")
        elif c.name in ("em", "i"):
            out.append(r"\emph{" + inline(c) + "}")
        elif c.name == "code":
            out.append(code(c.get_text()))
        elif c.name == "span" and "tag" in cls:
            txt = c.get_text().strip()
            out.append(r"\leantag{}" if txt == "Lean" else txt)
        elif c.name == "span" and "verify" in cls:
            out.append(r"\textcolor{orange}{" + inline(c) + "}")
        elif c.name == "span" and "lab" in cls:
            out.append(r"\textbf{" + inline(c) + "}")
        elif c.name == "br":
            out.append(r"\\ ")
        elif c.name == "sub":
            out.append(r"\textsubscript{" + inline(c) + "}")
        elif c.name == "sup":
            out.append(r"\textsuperscript{" + inline(c) + "}")
        else:
            out.append(inline(c))
    return "".join(out)


def table(div, labels):
    t = div.find("table")
    cap = t.find("caption")
    captxt = inline(cap) if cap else ""
    m = re.match(r"Table (\d+)\.\s*", cap.get_text() if cap else "")
    num = m.group(1) if m else None
    captxt = re.sub(r"^Table \d+\.\s*", "", captxt)
    head = [inline(th) for th in t.find("thead").find_all("th")] if t.find("thead") else []
    rows = []
    for tr in (t.find("tbody") or t).find_all("tr"):
        cells = tr.find_all("td")
        if cells:
            rows.append([(inline(td), "n" in (td.get("class") or [])) for td in cells])
    ncol = max([len(head)] + [len(r) for r in rows])
    numeric = [all(r[i][1] for r in rows if i < len(r)) and rows for i in range(ncol)]
    textlen = [max([len(head[i]) if i < len(head) else 0] + [len(r[i][0]) for r in rows if i < len(r)])
               for i in range(ncol)]
    wide = ncol >= 4 or sum(textlen) > 140
    spec = "".join(r">{\raggedleft\arraybackslash}X" if numeric[i] else r">{\raggedright\arraybackslash}X"
                   for i in range(ncol))
    env = "table*" if wide else "table"
    lab = f"\\label{{tab:{num}}}" if num else ""
    if num:
        labels.add(f"tab:{num}")
    lines = [f"\\begin{{{env}}}[!t]", r"\centering\footnotesize", f"\\caption{{{captxt}}}{lab}",
             f"\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}", r"\toprule"]
    if head:
        lines.append(" & ".join(r"\textbf{" + h + "}" for h in head) + r" \\ \midrule")
    for r in rows:
        lines.append(" & ".join(c for c, _ in r) + r" \\")
    lines += [r"\bottomrule", r"\end{tabularx}", f"\\end{{{env}}}"]
    return "\n".join(lines) + "\n"


FIG1 = r"""\begin{figure*}[!t]
\centering
\begin{tikzpicture}[node distance=2.6cm, every node/.style={font=\footnotesize},
  box/.style={draw, rounded corners=2pt, minimum width=2.0cm, minimum height=0.9cm, align=center},
  ok/.style={-{Latex}, thick, draw=green!50!black}, bad/.style={-{Latex}, thick, draw=red!70!black}]
\node[box] (u) {$u$\\[-1pt]{\scriptsize database}};
\node[box, right=of u] (v) {$v$\\[-1pt]{\scriptsize load bal.}};
\node[box, right=of v] (w) {$w$\\[-1pt]{\scriptsize gateway}};
\node[box, right=of w] (z) {$z$\\[-1pt]{\scriptsize clients}};
\draw[ok] (u) -- node[below=2pt, align=center, text=green!40!black]{$e_1$ hybrid\\ $T=\infty$, $O=0.1$} (v);
\draw[bad] (v) -- node[below=2pt, align=center, text=red!60!black]{$e_2$ RSA kex\\ $T=T_{\mathrm{Q}}$, $O=0.5$} (w);
\draw[bad] (w) -- node[below=2pt, align=center, text=red!60!black]{$e_3$ X25519\\ $T=T_{\mathrm{Q}}$, $O=1.0$} (z);
\end{tikzpicture}
\caption{CAPTION}\label{fig:1}
\end{figure*}
"""


def block(node, labels, ctx):
    """Block-level conversion of children of node."""
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            if str(c).strip():
                out.append(conv_text(str(c)) + "\n")
            continue
        if not isinstance(c, Tag):
            continue
        cls = c.get("class") or []
        if c.name == "h2":
            title = c.get_text().strip()
            m = re.match(r"(\d+)\.\s*(.*)", title)
            ma = re.match(r"Appendix ([A-Z])\.\s*(.*)", title)
            if m:
                labels.add(f"sec:{m.group(1)}")
                out.append(f"\n\\section{{{conv_text(m.group(2))}}}\\label{{sec:{m.group(1)}}}\n")
            elif ma:
                letter = "C" if ma.group(1) == "D" else ma.group(1)
                if not ctx.get("appendices"):
                    out.append("\n\\appendices\n")
                    ctx["appendices"] = True
                labels.add(f"app:{letter}")
                out.append(f"\n\\section{{{conv_text(ma.group(2))}}}\\label{{app:{letter}}}\n")
            else:
                out.append(f"\n\\section*{{{conv_text(title)}}}\n")
        elif c.name == "h3":
            title = c.get_text().strip()
            m = re.match(r"(\d+\.\d+)\s*(.*)", title)
            if m:
                labels.add(f"sec:{m.group(1)}")
                out.append(f"\n\\subsection{{{conv_text(m.group(2))}}}\\label{{sec:{m.group(1)}}}\n")
            else:
                out.append(f"\n\\subsection*{{{conv_text(title)}}}\n")
        elif c.name == "p":
            out.append("\n" + inline(c).strip() + "\n")
        elif c.name in ("ul", "ol"):
            env = "itemize" if c.name == "ul" else "enumerate"
            opt = "[label=(\\alph*)]" if c.get("type") == "a" else ""
            if "refs" in cls:
                continue
            items = [r"\item " + inline(li).strip() for li in c.find_all("li", recursive=False)]
            out.append(f"\n\\begin{{{env}}}{opt}\n" + "\n".join(items) + f"\n\\end{{{env}}}\n")
        elif c.name == "div" and "tbl" in cls:
            out.append(table(c, labels))
        elif c.name == "div" and "math" in cls:
            out.append("\n" + conv_text(c.get_text()).strip() + "\n")
        elif c.name == "div" and "env" in cls:
            out.append("\n\\begin{envblock}\n" + block(c, labels, ctx) + "\\end{envblock}\n")
        elif c.name == "figure":
            cap = c.find("figcaption")
            captxt = re.sub(r"^Figure 1\.\s*", "", inline(cap)) if cap else ""
            labels.add("fig:1")
            out.append(FIG1.replace("CAPTION", captxt))
        elif c.name == "pre":
            out.append("\n\\begin{figure*}[!t]\n\\begin{Verbatim}[fontsize=\\footnotesize, frame=lines]\n"
                       + c.get_text().strip("\n") + "\n\\end{Verbatim}\n"
                       "\\caption{Propagation over the condensation DAG (Appendix A).}\\label{fig:alg}\n\\end{figure*}\n")
        elif c.name in ("div", "section", "main", "figure"):
            out.append(block(c, labels, ctx))
    return "".join(out)


SPECIAL_KEYS = [("SP 1800-38", "nist-sp1800-38"), ("SP 800-208", "nist-sp800-208"), ("FIPS 203", "nist-fips203-205"),
                ("IR 8547", "nist-ir8547"), ("Commercial National Security", "nsa-cnsa2"), ("CycloneDX", "cyclonedx16")]

# first mentions that cite a reference by name rather than by author and year
ANCHORS = [("3DES (Sweet32)", "3DES (Sweet32~\\cite{bhargavan2016})"),
           ("(Carré, 1979; Mohri, 2002)", "\\cite{carre1979,mohri2002}"),
           ("(Mosca, 2018; preprint 2015)", "\\cite{mosca2018} (preprint 2015)"),
           ("(FIPS 205)", "(FIPS 205)~\\cite{nist-fips203-205}"),
           ("(SP 800-208)", "(SP 800-208~\\cite{nist-sp800-208})"),
           ("NIST IR 8547 (initial public draft)", "NIST IR 8547~\\cite{nist-ir8547} (initial public draft)"),
           ("NSA's CNSA 2.0", "NSA's CNSA 2.0~\\cite{nsa-cnsa2}"),
           ("(SP 1800-38)", "(SP 1800-38~\\cite{nist-sp1800-38})"),
           ("(as in TLS 1.3)", "(as in TLS 1.3~\\cite{rescorla2018})"),
           ("(RFC 4998)", "(RFC 4998~\\cite{gondrom2007})"),
           ("Tarjan's algorithm and", "Tarjan's algorithm~\\cite{tarjan1972} and")]


def bib_key(text, used):
    import unicodedata
    for needle, k in SPECIAL_KEYS:
        if needle in text and k not in used:
            used.add(k)
            return k
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    m = re.match(r"\s*([^\s,.(]+)", text)
    base = (m.group(1) if m else "ref").lower()
    base = re.sub(r"[^a-z]", "", base) or "ref"
    y = re.search(r"\((\d{4})\)", text)
    k = base + (y.group(1) if y else "")
    while k in used:
        k += "x"
    used.add(k)
    return k


def main():
    soup = BeautifulSoup(open(SRC).read(), "html.parser")
    labels, ctx = set(), {}
    title = soup.find("h1").get_text().strip()
    subtitle = soup.find("p", class_="subtitle").get_text().strip()
    abstract = soup.find("div", class_="abstract")
    abs_paras = [inline(p).strip() for p in abstract.find_all("p") if "kw" not in (p.get("class") or [])]
    kw = abstract.find("p", class_="kw").get_text().split(":", 1)[1].strip()

    body = []
    for sec in soup.find_all("section"):
        sid = sec.get("id", "")
        if sid in ("appC", "refs") or sec.find("div", class_="note"):
            continue
        body.append(block(sec, labels, ctx))
    text = "".join(body)

    # references
    used, bib = set(), []
    for li in soup.find("ol", class_="refs").find_all("li", recursive=False):
        plain = li.get_text()
        bib.append((bib_key(plain, used), inline(li).strip(), plain))

    # citations: narrative "Name ... (YYYY)" and parenthetical "(Name ..., YYYY)"
    def first_surname(plain):
        return re.match(r"\s*([^\s,.(\[]+)", plain).group(1)
    for key, _, plain in bib:
        if plain.startswith("["):
            text = re.sub(r"\(\\emph\{Cybersecurity\}, 2026\)", rf"\\cite{{{key}}}", text)
            continue
        sn = esc_text(first_surname(plain))
        y = re.search(r"\((\d{4})\)", plain)
        if not y:
            if sn == "Mosca" and "Piani" in plain:
                text = text.replace(r"(Mosca \& Piani)", rf"\cite{{{key}}}")
            continue
        yr = y.group(1)
        text = re.sub(rf"\({re.escape(sn)}[^()]{{0,90}}?, {yr}\)", rf"\\cite{{{key}}}", text)
        text = re.sub(rf"({re.escape(sn)}(?: et al\.|(?:,| \\&| and)[^()]{{0,80}}?)?) \({yr}\)",
                      rf"\1~\\cite{{{key}}}", text)

    # name-only first mentions (Verbatim blocks are left untouched)
    verb = re.findall(r"\\begin\{Verbatim\}.*?\\end\{Verbatim\}", text, re.S)
    for i, v in enumerate(verb):
        text = text.replace(v, f"@@VERB{i}@@")
    for a, b in ANCHORS:
        if a in text:
            text = text.replace(a, b.replace("\\\\", "\\"), 1)
        else:
            print("anchor not found:", a)
    i0 = text.find("CycloneDX")
    if i0 >= 0:
        j = text.find(" ", text.find("CycloneDX 1.6", i0) + 13) if "CycloneDX 1.6" in text else i0 + 9
        text = text[:j] + "~\\cite{cyclonedx16}" + text[j:]
    for i, v in enumerate(verb):
        text = text.replace(f"@@VERB{i}@@", v)

    # cross references
    def sec_ref(n):
        return rf"\ref{{sec:{n}}}" if f"sec:{n}" in labels else None

    def repl_range(m):
        a, b = m.group(1), m.group(2)
        if "." in a and "." not in b:
            b = a.split(".")[0] + "." + b if len(b) <= 2 and not sec_ref(b) else b
        ra, rb = sec_ref(a), sec_ref(b)
        return rf"Sections~{ra}--{rb}" if ra and rb else m.group(0)
    text = re.sub(r"(RFC \d+, )§(\d+(?:\.\d+)?)", r"\1Sec.~\2", text)
    text = re.sub(r"§§?(\d+(?:\.\d+)?)–(\d+(?:\.\d+)?)", repl_range, text)
    text = re.sub(r"§(\d+(?:\.\d+)?)", lambda m: ("Section~" + sec_ref(m.group(1))) if sec_ref(m.group(1)) else m.group(0), text)
    text = re.sub(r"Tables (\d+) and (\d+)", r"Tables~\\ref{tab:\1} and~\\ref{tab:\2}", text)
    text = re.sub(r"Table (\d+)(?!\d)", r"Table~\\ref{tab:\1}", text)
    text = re.sub(r"Figure 1\b", r"Fig.~\\ref{fig:1}", text)
    text = text.replace("Appendix D", "Appendix C")

    # order bibliography by first citation
    order = []
    keyed = {k: (b, p) for k, b, p in bib}
    for group in re.findall(r"\\cite\{([^}]+)\}", text):
        for k in group.split(","):
            if k not in keyed:
                print("cited key missing from bibliography:", k)
            elif k not in order:
                order.append(k)
    uncited = [k for k, _, _ in bib if k not in order]
    biblines = [f"\\bibitem{{{k}}} {keyed[k][0]}" for k in order + uncited]

    leftover = re.findall(r"[A-Z][a-zA-Zāėūš\\&,. ]{2,60}\(\d{4}\)|\([A-Z][^()]{0,60}, \d{4}\)", text)

    pre = r"""\documentclass[conference]{IEEEtran}
\usepackage{fontspec}
\setmainfont{texgyretermes}[Extension=.otf, UprightFont=*-regular, BoldFont=*-bold,
  ItalicFont=*-italic, BoldItalicFont=*-bolditalic]
\setmonofont{DejaVuSansMono}[Extension=.ttf, BoldFont=*-Bold, Scale=0.82]
\usepackage{amsmath,amssymb}
\usepackage{tabularx,booktabs,enumitem,fancyvrb,xcolor,tikz,cite}
\usetikzlibrary{positioning,arrows.meta}
\usepackage[hidelinks]{hyperref}
\newcommand{\Tq}{T_{\mathrm{Q}}}
\newcommand{\tfix}{t_{\mathrm{fix}}}
\newcommand{\Ch}{\mathrm{Ch}}
\renewcommand{\E}{\mathbb{E}}
\newcommand{\pos}[1]{\left[#1\right]^{+}}
\renewcommand{\lt}{<}
\renewcommand{\gt}{>}
\newcommand{\leantag}{\textsuperscript{\textsf{\scriptsize[Lean]}}}
\newenvironment{envblock}{\par\smallskip\noindent\ignorespaces}{\par\smallskip}
\setlist{leftmargin=*, nosep, topsep=2pt}
\begin{document}
"""
    pre = pre.replace(r"\renewcommand{\E}", r"\providecommand{\E}{}\renewcommand{\E}")
    pre = pre.replace(r"\renewcommand{\lt}", r"\providecommand{\lt}{}\renewcommand{\lt}")
    pre = pre.replace(r"\renewcommand{\gt}", r"\providecommand{\gt}{}\renewcommand{\gt}")
    head = (f"\\title{{{conv_text(title)}\\\\[4pt]\\large {conv_text(subtitle)}}}\n"
            "\\author{\\IEEEauthorblockN{Rick Glenn}\n\\IEEEauthorblockA{Technical Cofounder, Dytallix, Inc.\\\\\nrick@dytallix.com}}\n"
            "\\maketitle\n\\begin{abstract}\n" + "\n\n".join(abs_paras) + "\n\\end{abstract}\n"
            f"\\begin{{IEEEkeywords}}\n{conv_text(kw)}\n\\end{{IEEEkeywords}}\n")
    tail = "\n\\begin{thebibliography}{99}\n" + "\n".join(biblines) + "\n\\end{thebibliography}\n\\end{document}\n"
    # the Declarations section and the appendices: move appendices after the bibliography? IEEE
    # conference style places appendices before the references, which is what the source order gives.
    open(OUT, "w").write(pre + head + text + tail)
    print(f"wrote {OUT}: {len(order)} cited references, {len(uncited)} uncited, {len(labels)} labels")
    if leftover:
        print("possible unconverted citations:", *sorted(set(leftover))[:20], sep="\n  ")
    for m in sorted(set(re.findall(r"§[^ ]{0,12}", text))):
        print("unresolved section reference:", m)


if __name__ == "__main__":
    sys.exit(main())
