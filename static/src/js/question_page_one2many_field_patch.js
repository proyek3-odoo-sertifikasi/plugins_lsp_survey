/** @odoo-module **/

console.warn("[LSP DEBUG] FILE LOADED: question_page_one2many_field_patch.js");

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";

/**
 * V5: Position-based insertion via sequence management.
 *
 * FAKTA YANG SUDAH TERBUKTI (dari investigasi):
 * 1. onClose hook TERBUKTI terpanggil setelah dialog Save + persist selesai.
 * 2. newRecord.update({sequence: X}) TERBUKTI berhasil mengubah sequence
 *    dan memicu web_save dengan [[1, id, {sequence: X}]].
 * 3. Odoo mengelompokkan question ke section berdasarkan sequence order murni:
 *    section.seq < question.seq < next_section.seq → question masuk ke section tersebut.
 * 4. Masalah BUKAN page_id, BUKAN context, BUKAN create() — melainkan NILAI SEQUENCE.
 *
 * ALGORITMA V5:
 * - Saat button diklik: simpan target section (resId + sequence).
 * - Biarkan Odoo create question secara normal (sequence = last + 1).
 * - Di onClose: hitung sequence yang benar berdasarkan posisi section.
 *   - Jika ada gap antara target section dan section berikutnya → insert di gap.
 *   - Jika tidak ada gap (gap <= 1) → resequence seluruh survey (×10) terlebih dahulu,
 *     lalu assign sequence baru di dalam gap yang terbentuk.
 * - Update sequence via newRecord.update() yang sudah terbukti berhasil.
 * - Root record di-save untuk persist perubahan ke DB.
 */

setTimeout(() => {
    console.warn("[LSP DEBUG] INSIDE setTimeout");
    
    const fieldDef = registry.category("fields").get("question_page_one2many");
    console.warn("[LSP DEBUG] fieldDef =", fieldDef);

    if (!fieldDef || !fieldDef.component) {
        console.error("[LSP V5] Cannot find question_page_one2many in registry!");
        return;
    }

    const QuestionPageOneToManyField = fieldDef.component;
    console.warn("[LSP DEBUG] QuestionPageOneToManyField =", QuestionPageOneToManyField);

    patch(QuestionPageOneToManyField.prototype, {

        setup() {
            console.warn("[LSP P2] FIELD SETUP called");
            super.setup(...arguments);

            const originalOpenRecord = this._openRecord.bind(this);

            this._openRecord = async (params) => {
                console.warn("[LSP V5 DEBUG] _openRecord CALLED", params);
                
                // Snapshot resIds sebelum dialog dibuka
                const resIdsBefore = new Set(
                    (this.list ? this.list.records : []).map((r) => r.resId).filter(Boolean)
                );
                console.warn("[LSP V5 DEBUG] resIdsBefore:", Array.from(resIdsBefore));

                const originalOnClose = params.onClose;
                const wrappedParams = {
                    ...params,
                    onClose: async (...args) => {
                        console.warn("[LSP V5 DEBUG] onClose FIRED");
                        // onClose terbukti terpanggil SETELAH dialog Save + persist
                        await this._lspV5PositionNewQuestion(resIdsBefore);

                        if (originalOnClose) {
                            return originalOnClose(...args);
                        }
                    },
                };

                return originalOpenRecord(wrappedParams);
            };
        },

        /**
         * V5 Core Logic: Posisikan question baru di bawah target section.
         *
         * @param {Set} resIdsBefore - Set resIds sebelum dialog dibuka
         */
        async _lspV5PositionNewQuestion(resIdsBefore) {
            console.warn("[LSP V5 DEBUG] _lspV5PositionNewQuestion CALLED");
            const list = this.list;
            if (!list) {
                console.warn("[LSP V5 DEBUG] this.list is missing!");
                return;
            }

            // Ambil target section dari state global (window)
            const targetSection = window.__lspTargetSection;
            console.warn("[LSP V5 DEBUG] window.__lspTargetSection =", targetSection);
            
            delete window.__lspTargetSection;

            if (!targetSection) {
                console.warn("[LSP V5 DEBUG] No targetSection found, aborting position update.");
                // Bukan klik dari tombol LSP kita — tidak perlu reposition
                return;
            }

            const listRecords = list.records;
            console.warn("[LSP V5 DEBUG] All list records:", listRecords.map(r => ({ 
                resId: r.resId, 
                seq: r.data.sequence, 
                page_id: r.data.page_id,
                is_page: r.data.is_page,
                title: r.data.title || r.data.value_char_box
            })));

            // Temukan question yang baru dibuat
            const newRecord = listRecords.find(
                (r) => r.resId && !resIdsBefore.has(r.resId) && !r.data.is_page
            );

            if (!newRecord) {
                console.warn("[LSP V5 DEBUG] Could not find newRecord! Either user cancelled, or resId is missing.");
                return;
            }

            console.warn(
                "[LSP CHECK]",
                "resId=", newRecord.resId,
                "page_id=", newRecord.data.page_id,
                "sequence=", newRecord.data.sequence
            );
            console.warn("[LSP V5 DEBUG] Target section:", targetSection);

            // Hitung target sequence berdasarkan posisi
            const targetSeq = await this._lspV5ComputeAndEnsureGap(
                listRecords, targetSection, newRecord
            );

            if (targetSeq === null) {
                console.warn("[LSP V5] Could not compute target sequence.");
                return;
            }

            if (targetSeq === newRecord.data.sequence) {
                console.log("[LSP V5] Sequence already correct:", targetSeq);
                return;
            }

            console.log("[LSP V5] Updating sequence:", newRecord.data.sequence, "→", targetSeq);

            // Update via newRecord.update() — TERBUKTI bekerja dari investigasi
            try {
                // V6: UPDATE SEQUENCE AND PAGE_ID
                // page_id is the root cause of section grouping issues.
                const updatePayload = { sequence: targetSeq };
                if (targetSection.resId) {
                    updatePayload.page_id = [targetSection.resId, targetSection.title || ""];
                }
                
                await newRecord.update(updatePayload);
                console.warn("[LSP V6 DEBUG] Sequence & page_id updated. Saving...");
                await this.props.record.save();
                console.warn("[LSP V6 DEBUG] Save complete. Question positioned correctly.");
            } catch (err) {
                console.error("[LSP V6 DEBUG] Failed to update sequence/page_id:", err);
            }
        },

        /**
         * Hitung sequence target untuk question baru.
         * Jika gap tidak mencukupi, resequence seluruh survey terlebih dahulu.
         *
         * @param {Array} records - seluruh records di list
         * @param {Object} targetSection - {resId, sequence} dari section yang diklik
         * @param {Object} newRecord - OWL record dari question baru
         * @returns {number|null} - sequence yang harus di-assign ke question baru
         */
        async _lspV5ComputeAndEnsureGap(records, targetSection, newRecord) {
            // Temukan posisi target section dan next section dalam records
            // Records diurutkan berdasarkan sequence di client
            const sortedRecords = [...records].sort(
                (a, b) => (a.data.sequence || 0) - (b.data.sequence || 0)
            );

            const targetIdx = sortedRecords.findIndex(
                (r) => r.resId === targetSection.resId && r.data.is_page
            );

            if (targetIdx === -1) {
                console.warn("[LSP V5] Target section not found in sorted records.");
                return null;
            }

            // Cari section berikutnya setelah target section
            let nextSectionRecord = null;
            for (let i = targetIdx + 1; i < sortedRecords.length; i++) {
                if (sortedRecords[i].data.is_page) {
                    nextSectionRecord = sortedRecords[i];
                    break;
                }
            }

            const currentSectionSeq = sortedRecords[targetIdx].data.sequence || 0;
            const nextSectionSeq = nextSectionRecord
                ? nextSectionRecord.data.sequence
                : null;

            console.log("[LSP V5] currentSectionSeq:", currentSectionSeq);
            console.log("[LSP V5] nextSectionSeq:", nextSectionSeq);

            // Hitung gap
            const gap = nextSectionSeq !== null
                ? nextSectionSeq - currentSectionSeq
                : null;

            console.log("[LSP V5] gap:", gap);

            if (gap === null) {
                // Tidak ada section berikutnya — cukup taruh setelah section
                // Kumpulkan question yang sudah ada di section ini (selain newRecord)
                const existingInSection = [];
                for (let i = targetIdx + 1; i < sortedRecords.length; i++) {
                    const r = sortedRecords[i];
                    if (r.data.is_page) break;
                    if (r.resId !== newRecord.resId) existingInSection.push(r);
                }
                if (existingInSection.length > 0) {
                    const lastSeq = existingInSection[existingInSection.length - 1].data.sequence;
                    return lastSeq + 1;
                }
                return currentSectionSeq + 1;
            }

            if (gap > 1) {
                // Ada gap yang cukup — hitung sequence di antara sections
                // Kumpulkan question yang sudah ada di section ini (selain newRecord)
                const existingInSection = [];
                for (let i = targetIdx + 1; i < sortedRecords.length; i++) {
                    const r = sortedRecords[i];
                    if (r.data.is_page) break;
                    if (r.resId !== newRecord.resId) existingInSection.push(r);
                }

                if (existingInSection.length === 0) {
                    // Section masih kosong — masuk tepat setelah section
                    return currentSectionSeq + 1;
                }

                const lastExistingSeq = existingInSection[existingInSection.length - 1].data.sequence;
                if (lastExistingSeq < nextSectionSeq - 1) {
                    return lastExistingSeq + 1;
                }
                // Tidak ada ruang di antara question terakhir dan next section
                // Fall through ke resequence
            }

            // gap <= 1 atau tidak ada ruang — perlu resequence seluruh survey
            console.log("[LSP V5] Gap insufficient. Resequencing entire survey...");
            await this._lspV5ResequenceAll(sortedRecords, newRecord);

            // Setelah resequence, records sudah berubah — baca ulang dari list
            const freshRecords = [...(this.list ? this.list.records : [])].sort(
                (a, b) => (a.data.sequence || 0) - (b.data.sequence || 0)
            );

            const freshTargetIdx = freshRecords.findIndex(
                (r) => r.resId === targetSection.resId && r.data.is_page
            );
            if (freshTargetIdx === -1) return null;

            let freshNextSectionRecord = null;
            for (let i = freshTargetIdx + 1; i < freshRecords.length; i++) {
                if (freshRecords[i].data.is_page) {
                    freshNextSectionRecord = freshRecords[i];
                    break;
                }
            }

            const freshSectionSeq = freshRecords[freshTargetIdx].data.sequence;

            // Kumpulkan question yang sudah ada di section setelah resequence
            const freshExistingInSection = [];
            for (let i = freshTargetIdx + 1; i < freshRecords.length; i++) {
                const r = freshRecords[i];
                if (r.data.is_page) break;
                if (r.resId !== newRecord.resId) freshExistingInSection.push(r);
            }

            if (freshExistingInSection.length > 0) {
                const freshLastSeq = freshExistingInSection[freshExistingInSection.length - 1].data.sequence;
                return freshLastSeq + 10;
            }
            return freshSectionSeq + 10;
        },

        /**
         * Resequence seluruh survey dengan step ×10.
         * Setelah ini, setiap section/question memiliki gap 10 antar-sequence.
         *
         * @param {Array} sortedRecords - records yang sudah diurutkan berdasarkan sequence
         * @param {Object} excludeRecord - record yang TIDAK akan di-update (question baru)
         */
        async _lspV5ResequenceAll(sortedRecords, excludeRecord) {
            let seq = 10;
            for (const r of sortedRecords) {
                if (r.resId === excludeRecord.resId) {
                    seq += 10; // Tetap tingkatkan counter tapi skip update
                    continue;
                }
                try {
                    await r.update({ sequence: seq });
                } catch (err) {
                    console.warn("[LSP V5] Failed to resequence record", r.resId, err);
                }
                seq += 10;
            }
            // Simpan resequence ke DB
            await this.props.record.save();
            console.log("[LSP V5] Resequence complete. New sequences assigned.");
        },
    });
}, 0);
