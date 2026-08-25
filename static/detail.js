"use strict";

/* Book detail: bible sections plus inline editing.
   Saving sends one top-level bible key to PATCH /api/books/<slug>/bible, which
   merges it as-is: the endpoint does not re-run the generation schema check, so
   the 5-8 lines bound and the #RRGGBB shape are enforced here before sending. */

(function (LF) {
  const el = LF.el;
  const button = LF.button;
  const LINES_MIN = 5;
  const LINES_MAX = 8;

  const titleNode = document.getElementById("detail-title");
  const statusNode = document.getElementById("detail-status");
  const navNode = document.getElementById("detail-nav");
  const sectionsNode = document.getElementById("detail-sections");
  const generateBtn = document.getElementById("detail-generate");

  const state = { slug: null, book: null };

  // -- saving --------------------------------------------------------------
  async function patch(partial) {
    render(await LF.request("PATCH", "/api/books/" + state.slug + "/bible", partial));
  }

  function patchAt(list, index, key, changes) {
    const next = list.map((entry, position) =>
      position === index ? Object.assign({}, entry, changes) : entry
    );
    return patch({ [key]: next });
  }

  // -- editing -------------------------------------------------------------
  /* Read mode shows the value with an Edit button; Edit swaps in an input and
     Save/Cancel. Save hands the raw string to `commit`, which builds the patch. */
  function editable(value, multiline, commit) {
    const wrap = el("div", "editable");

    function readMode() {
      wrap.replaceChildren();
      wrap.appendChild(el("p", "field-value", value));
      wrap.appendChild(button("Edit", "btn btn-small", editMode));
    }

    function editMode() {
      wrap.replaceChildren();
      const input = el(multiline ? "textarea" : "input", "input");
      if (multiline) input.rows = 4;
      input.value = value;
      wrap.appendChild(input);
      const actions = el("div", "edit-actions");
      actions.appendChild(
        button("Save", "btn btn-primary btn-small", async () => {
          try {
            await commit(input.value);
          } catch (err) {
            LF.showNotice("Save failed: " + err.message, "error");
            readMode();
          }
        })
      );
      actions.appendChild(button("Cancel", "btn btn-small", readMode));
      wrap.appendChild(actions);
      input.focus();
    }

    readMode();
    return wrap;
  }

  function fieldRow(field, label, value, multiline, commit) {
    const row = el("div", "field-row");
    row.dataset.field = field;
    row.appendChild(el("span", "field-label", label));
    row.appendChild(editable(value == null ? "" : String(value), multiline, commit));
    return row;
  }

  function textRow(bible, key, label) {
    return fieldRow(key, label, bible[key] || "", true, (value) => patch({ [key]: value }));
  }

  // -- sections ------------------------------------------------------------
  function profileSection(bible) {
    const box = el("div", "stack");
    const profile = bible.profile && typeof bible.profile === "object" ? bible.profile : {};
    box.appendChild(
      fieldRow("name", "Name", bible.name || "", false, (value) => patch({ name: value }))
    );
    ["age", "role", "body"].forEach((key) =>
      box.appendChild(
        fieldRow("profile." + key, key, profile[key] || "", false, (value) =>
          patch({ profile: Object.assign({}, profile, { [key]: value }) })
        )
      )
    );
    const traits = Array.isArray(profile.traits) ? profile.traits : [];
    box.appendChild(
      fieldRow("profile.traits", "traits (one per line)", traits.join("\n"), true, (value) =>
        patch({
          profile: Object.assign({}, profile, {
            traits: value.split("\n").map((item) => item.trim()).filter(Boolean),
          }),
        })
      )
    );
    return box;
  }

  function voiceSection(bible) {
    const box = el("div", "stack");
    const voice = bible.voice && typeof bible.voice === "object" ? bible.voice : {};
    ["personality", "speech"].forEach((key) =>
      box.appendChild(
        fieldRow("voice." + key, key, voice[key] || "", true, (value) =>
          patch({ voice: Object.assign({}, voice, { [key]: value }) })
        )
      )
    );
    return box;
  }

  function linesSection(bible) {
    const lines = Array.isArray(bible.lines) ? bible.lines : [];
    const box = el("div", "stack");
    lines.forEach((entry, index) => {
      const item = el("div", "line-item");
      item.dataset.line = String(index);
      item.appendChild(
        fieldRow("lines." + index + ".situation", "situation", entry.situation || "", false,
          (value) => patchAt(lines, index, "lines", { situation: value }))
      );
      item.appendChild(
        fieldRow("lines." + index + ".line", "line", entry.line || "", true,
          (value) => patchAt(lines, index, "lines", { line: value }))
      );
      const remove = button("Remove", "btn btn-small btn-danger", () =>
        patch({ lines: lines.filter((_, position) => position !== index) })
      );
      remove.disabled = lines.length <= LINES_MIN;
      remove.title = remove.disabled ? "A bible keeps at least " + LINES_MIN + " lines" : "";
      item.appendChild(remove);
      box.appendChild(item);
    });
    const add = button("Add line", "btn btn-small", () =>
      patch({ lines: lines.concat([{ situation: "new situation", line: "new line" }]) })
    );
    add.disabled = lines.length >= LINES_MAX;
    add.title = add.disabled ? "A bible keeps at most " + LINES_MAX + " lines" : "";
    box.appendChild(add);
    return box;
  }

  function paletteSection(bible) {
    const palette = Array.isArray(bible.palette) ? bible.palette : [];
    const box = el("div", "stack");
    palette.forEach((color, index) => {
      const row = el("div", "swatch-row");
      row.dataset.swatch = String(index);
      const head = el("div", "swatch-head");
      head.appendChild(LF.paintSwatch(el("span", "swatch swatch-lg"), color.hex));
      head.appendChild(el("code", "swatch-hex", color.hex || "—"));
      row.appendChild(head);
      row.appendChild(
        fieldRow("palette." + index + ".name", "name", color.name || "", false,
          (value) => patchAt(palette, index, "palette", { name: value }))
      );
      row.appendChild(
        fieldRow("palette." + index + ".hex", "hex", color.hex || "", false, (value) => {
          const hex = value.trim();
          if (!LF.HEX_RE.test(hex)) throw new Error("hex must look like #RRGGBB");
          return patchAt(palette, index, "palette", { hex: hex });
        })
      );
      box.appendChild(row);
    });
    return box;
  }

  function promptSection(bible) {
    const box = el("div", "stack");
    const prompt = bible.master_prompt || "";
    const pre = el("pre", "code", prompt);
    pre.id = "master-prompt";
    box.appendChild(pre);
    const copy = button("Copy", "btn btn-small", async () => {
      try {
        await navigator.clipboard.writeText(prompt);
        copy.textContent = "Copied";
      } catch (err) {
        copy.textContent = "Copy failed";
      }
    });
    copy.id = "copy-prompt";
    box.appendChild(copy);
    box.appendChild(textRow(bible, "master_prompt", "edit prompt"));
    return box;
  }

  const SECTIONS = [
    { id: "profile", title: "Profile", build: profileSection },
    { id: "background", title: "Background", build: (b) => textRow(b, "background", "Background") },
    { id: "voice", title: "Voice", build: voiceSection },
    { id: "lines", title: "Lines", build: linesSection },
    { id: "palette", title: "Palette", build: paletteSection },
    { id: "world", title: "World", build: (b) => textRow(b, "world", "World") },
    { id: "prompt", title: "Master Prompt", build: promptSection },
  ];

  // -- rendering -----------------------------------------------------------
  function sectionPanel(spec, bible) {
    const panel = el("section", "panel");
    panel.id = "section-" + spec.id;
    const head = el("div", "panel-head");
    head.appendChild(el("h3", "panel-title", spec.title));
    panel.appendChild(head);
    panel.appendChild(spec.build(bible));
    return panel;
  }

  function render(book) {
    state.book = book;
    const bible = book.bible && typeof book.bible === "object" ? book.bible : null;
    titleNode.textContent = (bible && bible.name) || "(untitled)";
    statusNode.textContent = book.status || "empty";
    setGenerateLabel();
    navNode.replaceChildren();
    sectionsNode.replaceChildren();
    if (!bible) {
      const panel = el("section", "panel");
      panel.appendChild(el("p", "empty", "No bible yet. Use Generate to draft one."));
      panel.appendChild(el("p", "card-text", book.concept || ""));
      sectionsNode.appendChild(panel);
      return;
    }
    SECTIONS.forEach((spec) => {
      const target = sectionPanel(spec, bible);
      sectionsNode.appendChild(target);
      navNode.appendChild(
        button(spec.title, "navlink", () => target.scrollIntoView({ behavior: "smooth" }))
      );
    });
  }

  function setGenerateLabel() {
    generateBtn.textContent = state.book && state.book.bible ? "Regenerate" : "Generate";
  }

  generateBtn.addEventListener("click", async () => {
    generateBtn.disabled = true;
    generateBtn.textContent = "Generating…";
    try {
      render(await LF.generate(state.slug));
      LF.clearNotice();
    } catch (err) {
      if (err.status === 503) LF.showNotice(LF.NO_KEY_MESSAGE, "warn");
      else LF.showNotice("Generation failed: " + err.message, "error");
    } finally {
      generateBtn.disabled = false;
      setGenerateLabel();
    }
  });

  LF.openDetail = async function (slug) {
    state.slug = slug;
    state.book = null;
    titleNode.textContent = slug;
    try {
      render(await LF.request("GET", "/api/books/" + slug));
    } catch (err) {
      navNode.replaceChildren();
      sectionsNode.replaceChildren();
      const panel = el("section", "panel");
      panel.appendChild(el("p", "empty", "Could not load this book: " + err.message));
      sectionsNode.appendChild(panel);
    }
  };
})(window.LF);
