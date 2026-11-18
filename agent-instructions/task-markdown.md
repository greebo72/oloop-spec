## oloop Markdown-Dateien

Beim Erstellen oder Bearbeiten von oloop-Task-Dateien gelten diese Regeln:

- YAML-Frontmatter und Markdown-Text getrennt halten. Vorhandenes Frontmatter unverändert lassen, außer eine Änderung ist ausdrücklich gewünscht.
- Im Beschreibungstext gültiges Markdown verwenden, das der oloop-Markdown-Renderer unterstützt.
- Aufzählungen als echte Markdown-Listen schreiben: nummerierte Punkte jeweils in einer eigenen Zeile mit `1.`, `2.` usw.; ungeordnete Punkte jeweils in einer eigenen Zeile mit `-`. Keine Inline-Aufzählungen wie `(1) ... (2) ...`.
- Tabellen als GFM-Pipe-Tabellen schreiben. Eine Kopfzeile muss direkt von einer Trennzeile gefolgt werden; jede Tabellenzeile muss dieselbe Anzahl von Spalten haben. Beispiel:

  ```markdown
  | AP | Beschreibung | Status |
  | --- | --- | --- |
  | AP1 | Beispiel | offen |
  ```

- Um Listen und Tabellen Leerzeilen setzen. Ein wörtliches Pipe-Zeichen innerhalb einer Tabellenzelle als `\|` schreiben.
- Keine HTML-Tabellen oder HTML-Formatierung verwenden. Der Renderer stellt HTML derzeit als Text dar.
- Spaltenbreiten nicht über unterschiedlich lange Trennstriche vorgeben. Die Spaltenbreiten werden vom oloop-Renderer anhand des Inhalts verteilt.
