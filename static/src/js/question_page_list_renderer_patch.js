/** @odoo-module **/

import { QuestionPageListRenderer } from "@survey/question_page/question_page_list_renderer";
import { patch } from "@web/core/utils/patch";
import { useEffect } from "@odoo/owl";

patch(QuestionPageListRenderer.prototype, {

    setup() {
        super.setup(...arguments);

        useEffect(
            () => {
                const table = this.tableRef?.el;
                if (table) {
                    this._lspInjectButtons(table);
                }
                return () => {
                    const t = this.tableRef?.el;
                    if (t) {
                        t.querySelectorAll(".o_lsp_section_add_row")
                         .forEach((el) => el.remove());
                    }
                };
            }
            // Hapus array dependency agar selalu dijalankan tiap ada perubahan DOM (rerender)
        );
    },

    _lspInjectButtons(table) {
        const tbody = table.querySelector("tbody");
        if (!tbody) return;

        // Bersihkan sisa tombol lama sebelum render yang baru
        tbody.querySelectorAll(".o_lsp_section_add_row")
             .forEach(el => el.remove());

        const rows = Array.from(tbody.querySelectorAll("tr.o_data_row"));
        const sections = [];
        let current = null;

        for (const row of rows) {
            if (row.classList.contains("o_is_section")) {
                const recordId = row.dataset.id;
                const rec = this.props.list.records.find((r) => r.id === recordId);
                if (!rec) continue;
                current = { row, lastRow: row, record: rec };
                sections.push(current);
            } else if (current) {
                current.lastRow = row;
            }
        }

        // Sembunyikan "Add a question" di footer jika ada section
        const wrapper = table.closest(".o_field_x2many");
        const footer = wrapper?.querySelector(".o_field_x2many_list_row_add");
        if (footer) {
            const addQLink = footer.querySelector('a[name="add_question_control"]');
            if (addQLink) {
                addQLink.style.display = sections.length > 0 ? "none" : "";
            }
        }

        for (const section of sections) {
            const tr = document.createElement("tr");
            tr.className = "o_lsp_section_add_row";
            tr.style.cssText = "background: transparent;";

            const td = document.createElement("td");
            td.colSpan = 99;
            td.style.cssText = "padding: 4px 0 4px 48px; border: none;";

            const btn = document.createElement("a");
            btn.href = "#";
            btn.className = "text-primary";
            btn.style.cssText = "font-size: 0.85em; text-decoration: none;";
            btn.innerHTML = '<i class="fa fa-plus me-1"></i>Add a question';

            const capturedSection = section;

            btn.addEventListener("click", async (ev) => {
                ev.preventDefault();
                ev.stopPropagation();

                const root = this.props.list.model.root;
                if (root && root.isDirty) await root.save();

                let sectionResId = capturedSection.record.resId;
                if (!sectionResId) {
                    await root.save();
                    const freshRec = this.props.list.records.find(
                        (r) => r.id === capturedSection.record.id
                    );
                    if (!freshRec?.resId) {
                        console.error("[LSP V5] Section belum punya resId.");
                        return;
                    }
                    capturedSection.record = freshRec;
                    sectionResId = freshRec.resId;
                }

                // V5: Simpan target section di global object karena this.props.list ternyata tidak ter-share konsisten
                window.__lspTargetSection = {
                    resId: sectionResId,
                    sequence: capturedSection.record.data.sequence,
                    title: capturedSection.record.data.title || capturedSection.record.data.value_char_box || "",
                };
                // Buka dialog — biarkan Odoo create normal
                this.add({});
            });

            td.appendChild(btn);
            tr.appendChild(td);
            capturedSection.lastRow.after(tr);
        }
    },
});
