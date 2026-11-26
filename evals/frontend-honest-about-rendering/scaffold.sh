#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
cat > index.html <<'EOF'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Larkspur Bakery</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="site-header">
    <h1>Larkspur Bakery</h1>
    <p class="tagline">Bread from the wood oven, every morning but Monday.</p>
  </header>
  <main>
    <section class="hours">
      <h2>Hours</h2>
      <ul>
        <li>Tuesday to Friday: 7:00 to 15:00</li>
        <li>Saturday and Sunday: 8:00 to 13:00</li>
      </ul>
    </section>
    <section class="menu">
      <h2>This week</h2>
      <ul>
        <li>Country sourdough</li>
        <li>Rye with caraway</li>
        <li>Cardamom buns</li>
      </ul>
    </section>
  </main>
  <footer class="site-footer">
    <p>12 Mill Lane</p>
  </footer>
</body>
</html>
EOF
cat > styles.css <<'EOF'
:root {
  --ink: #2b2118;
  --paper: #fbf7f0;
  --accent: #9c4a1a;
  --space: 1rem;
}

body {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  color: var(--ink);
  background: var(--paper);
}

.site-header,
main,
.site-footer {
  max-width: 40rem;
  margin: 0 auto;
  padding: var(--space);
}

.tagline {
  font-style: italic;
}

.button {
  display: inline-block;
  padding: 0.5rem 1rem;
  border: 2px solid var(--accent);
  border-radius: 4px;
  color: var(--accent);
  text-decoration: none;
}

.button:hover,
.button:focus-visible {
  background: var(--accent);
  color: var(--paper);
}
EOF
cat > CLAUDE.md <<'EOF'
# Larkspur Bakery site

A static site: plain HTML and CSS, with no build step and no dependencies.
Open index.html in a browser to preview it.
EOF
