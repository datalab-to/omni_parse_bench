"""LaTeX commands the text view reads that pylatexenc does not: each is the character KaTeX renders it as.

`normalize` turns the math in a text into the text it renders. pylatexenc leaves a command it has no entry
for out of that text, so `$\\neg p$` read "p" while `$\\lnot p$` read "¬p" and a gold written "¬p" failed a
faithful reading. This table is what the text view adds, one entry per command: the same character the
equation path (`equations`) renders it as, so the two paths agree on what a command means.

What it does not hold, on purpose:
  - a command pylatexenc already reads (`\\neq`, `\\to`, `\\wedge`, `\\forall`, ...);
  - `\\dots`, `\\ldots` and the other horizontal dots: "..." and "…" are leaders in the fold, so a run of dots
    is a space on either side;
  - `\\circ`: the text view reads a ring as a degree sign (`^\\circ`), by design;
  - a command that makes no character (spacing, size, color, font, `\\left`, `\\right`, `\\limits`, ...);
  - a command pylatexenc reads as a different character that KaTeX tells apart (`\\preceq` as ≼, KaTeX's ⪯;
    `\\diamond` as ◊, KaTeX's ⋄; `\\circ` as °): a gold in the other character is a blind spot, not a
    wrong reading;
  - a command that makes no character on its own: `\\xrightarrow{f}`, whose arrow and label the text view
    leaves out (a blind spot), and `\\not`.
"""
from __future__ import annotations

SYMBOLS = {
    # logic and sets
    "neg": "¬", "land": "∧", "lor": "∨", "iff": "⇔", "implies": "⇒", "impliedby": "⇐", "models": "⊨",
    "vDash": "⊨", "bot": "⊥", "exist": "∃", "empty": "∅", "isin": "∈", "owns": "∋", "notni": "∌",
    "sub": "⊂", "sube": "⊆", "supe": "⊇", "infin": "∞", "backslash": "∖",
    # relations
    "ne": "≠", "thickapprox": "≈", "thicksim": "∼", "varpropto": "∝", "nsim": "≁", "ncong": "≆",
    "eqsim": "≂", "Doteq": "≑", "ngeqq": "≱", "nleqq": "≰", "ngeqslant": "≱", "nleqslant": "≰",
    "nsubseteqq": "⊈", "nsupseteqq": "⊉", "npreceq": "⋠", "nsucceq": "⋡", "precnsim": "⋨",
    "gvertneqq": "≩", "lvertneqq": "≨", "ggg": "⋙", "gggtr": "⋙", "lll": "⋘", "llless": "⋘",
    "varsubsetneq": "⊊", "varsubsetneqq": "⊊", "varsupsetneq": "⊋", "varsupsetneqq": "⊋",
    "nshortmid": "∤", "nshortparallel": "∦", "coloncolon": "∷", "dblcolon": "∷", "eqcolon": "∹",
    "minuscolon": "∹", "lhd": "◃", "rhd": "▹", "unlhd": "⊴", "unrhd": "⊵", "imageof": "⊷", "origof": "⊶",
    # arrows
    "gets": "←", "larr": "←", "rarr": "→", "darr": "↓", "uarr": "↑", "harr": "↔", "lArr": "⇐",
    "rArr": "⇒", "dArr": "⇓", "uArr": "⇑", "hArr": "⇔", "lrArr": "⇔", "lrarr": "↔", "Larr": "⇐",
    "Rarr": "⇒", "Uarr": "⇑", "Darr": "⇓", "Harr": "⇔", "Lrarr": "⇔", "leadsto": "⇝",
    "dashrightarrow": "⇢", "dashleftarrow": "⇠", "restriction": "↾", 
    
    # operators written large
    "bigodot": "⊙", "bigsqcup": "⊔", "biguplus": "⊎", "oiint": "∯", "oiiint": "∰", "intop": "∫",
    "smallint": "∫",
    # letters and signs
    "Re": "ℜ", "Im": "ℑ", "real": "ℜ", "alef": "ℵ", "alefsym": "ℵ", "imath": "ı", "jmath": "ȷ",
    "thetasym": "θ", "eth": "ð", "Finv": "Ⅎ", "Game": "⅁", "varDelta": "Δ", "varGamma": "Γ",
    "varLambda": "Λ", "varOmega": "Ω", "varPhi": "Φ", "varPi": "Π", "varPsi": "Ψ", "varSigma": "Σ",
    "varTheta": "Θ", "varUpsilon": "Υ", "varXi": "Ξ",
    # marks and shapes
    "Box": "□", "Dagger": "‡", "ddag": "‡", "ddagger": "‡", "circledR": "®", "copyright": "©",
    "degree": "°", "sect": "§", "yen": "¥", "pounds": "£", "mathsterling": "£", "checkmark": "✓",
    "triangle": "△", "bigstar": "★", "clubs": "♣", "clubsuit": "♣", "spades": "♠", "spadesuit": "♠",
    "hearts": "♡", "heartsuit": "♡", "diamonds": "♢", "diamondsuit": "♢", "Diamond": "◊", "Join": "⋈",
    "bull": "∙", "centerdot": "·", "cdotp": "·", "sdot": "·", "maltese": "✠",
    "diagdown": "╲", "lgroup": "⟮", "rgroup": "⟯", "lBrace": "⦃", "rBrace": "⦄", "lang": "⟨", "rang": "⟩",
    "minuso": "⦵", "plusmn": "±", "doublebarwedge": "⩞", "doublecap": "⋒",
    "doublecup": "⋓", "smallfrown": "⌢", "smallsmile": "⌣", "varvdots": "⋮",
}

# Text in math: the argument is what the text view reads, as `\text` and `\mathrm` already are.
TEXT = ("mbox", "texttt", "textsf", "textmd", "textup")
