import logging
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# Peta dari lsp_question_type ke question_type Odoo native
LSP_TYPE_TO_ODOO = {
    'pg': 'simple_choice',
    'essay': 'text_box',
    'praktikum': 'text_box',
    'observasi': 'char_box',
}


class SurveyQuestion(models.Model):
    _inherit = "survey.question"

    # Field untuk Section (is_page=True) yang merepresentasikan Unit Kompetensi
    # - title  (bawaan Odoo) = Nama Unit Kompetensi
    # - unit_code (tambahan) = Kode Unit Kompetensi
    unit_code = fields.Char(string="Kode Unit", help="Kode unit kompetensi, contoh: TIK.PR01.001.01")

    # lsp_question_type: selector tipe soal LSP (menggantikan question_type native di UI)
    # pg       → simple_choice (Pilihan Ganda, hanya 1 jawaban benar, skor otomatis 100)
    # essay    → text_box      (Esai, Multiple Lines Text Box)
    # praktikum→ text_box      (Praktikum, Multiple Lines Text Box, peserta isi "-")
    lsp_question_type = fields.Selection([
        ('pg', 'Pilihan Ganda'),
        ('essay', 'Esai'),
        ('praktikum', 'Praktikum'),
        ('observasi', 'Observasi'),
    ], string="Tipe Soal", default='pg', required=True)

    asesor_id = fields.Many2one(
        "res.users",
        string="Asesor Pembuat",
        default=lambda self: self.env.user,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting", "Waiting"),
            ("revise", "Revise"),
            ("active", "Active"),
        ],
        string="Status Validasi",
        default="draft",
        required=True,
    )
    catatan_admin = fields.Text(string="Catatan Admin")
    can_submit = fields.Boolean(compute="_compute_lsp_permissions")
    can_approve = fields.Boolean(compute="_compute_lsp_permissions")

    @api.depends_context("uid")
    def _compute_lsp_permissions(self):
        is_admin = self.env.user.has_group("plugins_manajement_asesor.group_admin_lsp")
        is_asesor = self.env.user.has_group("plugins_manajement_asesor.group_asesor")
        for question in self:
            question.can_submit = is_asesor
            question.can_approve = is_admin

    # ------------------------------------------------------------------
    # Onchange: sinkronisasi lsp_question_type → question_type Odoo
    # ------------------------------------------------------------------
    @api.onchange('lsp_question_type')
    def _onchange_lsp_question_type(self):
        """Sinkronkan lsp_question_type ke question_type Odoo dan terapkan aturan otomatis."""
        if self.is_page:
            return
        odoo_type = LSP_TYPE_TO_ODOO.get(self.lsp_question_type, 'simple_choice')
        self.question_type = odoo_type
        # Semua soal wajib dijawab
        self.constr_mandatory = True
        self.constr_error_msg = _("Jawaban wajib diisi.")

    # ------------------------------------------------------------------
    # Constraint: soal non-section wajib berada di bawah sebuah Section
    # ------------------------------------------------------------------
    @api.constrains('page_id', 'is_page')
    def _check_question_must_have_section(self):
        """Setiap soal (bukan section) WAJIB berada di bawah sebuah Unit Kompetensi (Section/Page)."""
        # Skip check jika dalam proses LSP resequence
        if self.env.context.get('lsp_skip_section_check'):
            return
        for question in self:
            if not question.is_page and not question.page_id:
                raise ValidationError(_(
                    "Setiap soal harus dimasukkan ke dalam sebuah Unit Kompetensi (Section). "
                    "Silakan buat atau pilih Section terlebih dahulu sebelum menambahkan soal."
                ))

    # ------------------------------------------------------------------
    # Create: paksa question_type + mandatory + skor PG otomatis
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Hanya LSP Asesor yang boleh membuat soal atau section baru."""
        if not self.env.context.get("lsp_allow_non_asesor_create") and not self.env.user.has_group(
            "plugins_manajement_asesor.group_asesor"
        ):
            raise AccessError(
                _(
                    "Hanya user dengan role LSP Asesor yang boleh membuat soal atau section. "
                    "LSP Admin hanya dapat menyetujui atau merevisi soal yang sudah dibuat."
                )
            )
        for vals in vals_list:
            if not vals.get('is_page'):
                lsp_type = vals.get('lsp_question_type', 'pg')
                # Paksa question_type sesuai mapping
                vals.setdefault('question_type', LSP_TYPE_TO_ODOO.get(lsp_type, 'simple_choice'))
                # Semua soal wajib dijawab
                vals.setdefault('constr_mandatory', True)
                vals.setdefault('constr_error_msg', _("Jawaban wajib diisi."))

        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Write: jaga sinkronisasi question_type saat lsp_question_type berubah
    # ------------------------------------------------------------------
    def write(self, vals):
        if 'lsp_question_type' in vals and not vals.get('is_page'):
            lsp_type = vals['lsp_question_type']
            if 'question_type' not in vals:
                vals['question_type'] = LSP_TYPE_TO_ODOO.get(lsp_type, 'simple_choice')
        return super().write(vals)

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------
    def action_submit(self):
        if not self.env.user.has_group("plugins_manajement_asesor.group_asesor"):
            raise AccessError(_("Hanya LSP Asesor yang bisa mengajukan validasi soal."))
        if any(question.state not in ("draft", "revise") for question in self):
            raise UserError(_("Status hanya bisa diajukan dari Draft or Revise."))
        self.write({"state": "waiting"})
        return True

    def action_approve(self):
        """Setujui soal/section → ubah status menjadi Active."""
        if not self.env.user.has_group("plugins_manajement_asesor.group_admin_lsp"):
            raise AccessError(_("Hanya LSP Admin yang bisa menyetujui soal."))
        already_active = self.filtered(lambda q: q.state == "active")
        if already_active:
            raise UserError(
                _("Soal berikut sudah berstatus Active: %s")
                % ", ".join(already_active.mapped("title"))
            )
        self.write({"state": "active"})
        return True

    def action_revise(self):
        if not self.env.user.has_group("plugins_manajement_asesor.group_admin_lsp"):
            raise AccessError(_("Hanya LSP Admin yang bisa meminta revisi."))
        if any(question.state != "waiting" for question in self):
            raise UserError(_("Status hanya bisa direvisi dari Waiting."))
        self.write({"state": "revise"})
        return True


class SurveyQuestionAnswer(models.Model):
    _inherit = "survey.question.answer"

    @api.model_create_multi
    def create(self, vals_list):
        """Saat opsi jawaban dibuat untuk soal PG (simple_choice),
        pastikan hanya 1 opsi yang bisa benar dan skor otomatis 100."""
        records = super().create(vals_list)
        for rec in records:
            if rec.question_id and rec.question_id.question_type == 'simple_choice':
                if rec.is_correct:
                    # Set skor ke 100
                    rec.answer_score = 100
                    # Pastikan opsi lain tidak benar
                    other_correct = rec.question_id.suggested_answer_ids.filtered(
                        lambda a: a.id != rec.id and a.is_correct
                    )
                    if other_correct:
                        other_correct.write({'is_correct': False, 'answer_score': 0})
        return records

    def write(self, vals):
        result = super().write(vals)
        for rec in self:
            if rec.question_id and rec.question_id.question_type == 'simple_choice':
                if vals.get('is_correct'):
                    # Auto set skor 100
                    if rec.answer_score != 100:
                        super(SurveyQuestionAnswer, rec).write({'answer_score': 100})
                    # Hapus flag benar dari opsi lain
                    other_correct = rec.question_id.suggested_answer_ids.filtered(
                        lambda a: a.id != rec.id and a.is_correct
                    )
                    if other_correct:
                        other_correct.write({'is_correct': False, 'answer_score': 0})
        return result


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    # -------------------------------------------------------------------------
    # Default Values: Optimasi UX agar Asesor/Admin tidak perlu konfigurasi manual
    # -------------------------------------------------------------------------
    questions_layout = fields.Selection(
        default='page_per_section',
    )
    access_mode = fields.Selection(
        default='public',
    )
    questions_selection = fields.Selection(
        default='random',
    )
    scoring_type = fields.Selection(
        default='scoring_with_answers',
    )

    def _lsp_filter_active_questions(self, questions):
        """Keep only approved questions and their parent sections for the participant-facing flow."""
        if self.env.context.get("lsp_include_inactive_questions"):
            return questions

        has_pages = any(q.is_page for q in questions)
        has_non_pages = any(not q.is_page for q in questions)

        if has_pages and not has_non_pages:
            all_non_page = self.question_and_page_ids.filtered(lambda q: not q.is_page)
            active_non_page = all_non_page.filtered(lambda q: q.state == "active")
            sections_with_active_q = active_non_page.mapped("page_id")
            return questions.filtered(lambda p: p in sections_with_active_q)

        active_questions = questions.filtered(lambda q: not q.is_page and q.state == "active")
        sections_with_active_q = active_questions.mapped("page_id")

        def _is_visible(q):
            if q.is_page:
                return q in sections_with_active_q
            if q.state != "active":
                return False
            if q.page_id and q.page_id not in sections_with_active_q:
                return False
            return True

        return questions.filtered(_is_visible)

    def _get_pages_or_questions(self, user_input):
        pages_or_questions = super()._get_pages_or_questions(user_input)
        return self._lsp_filter_active_questions(pages_or_questions)

    def _get_survey_questions(self, answer=None, page_id=None, question_id=None):
        questions, page_or_question_id = super()._get_survey_questions(
            answer=answer,
            page_id=page_id,
            question_id=question_id,
        )
        return self._lsp_filter_active_questions(questions), page_or_question_id

    def _get_next_page_or_question(self, user_input, page_or_question_id, go_back=False):
        """Override untuk mencegah ValueError saat navigasi survey."""
        pages_or_questions = self._get_pages_or_questions(user_input)
        if not pages_or_questions:
            return self.env["survey.question"]

        if page_or_question_id not in pages_or_questions.ids:
            if go_back:
                return self.env["survey.question"]
            return pages_or_questions[0]

        return super()._get_next_page_or_question(user_input, page_or_question_id, go_back=go_back)

    @api.depends("question_and_page_ids", "question_and_page_ids.state")
    def _compute_page_and_question_ids(self):
        """Override to expose only sections-with-active-questions and active questions."""
        super()._compute_page_and_question_ids()

        if self.env.context.get("lsp_include_inactive_questions"):
            return

        for survey in self:
            all_q = survey.question_and_page_ids.filtered(lambda q: not q.is_page)
            active_q = all_q.filtered(lambda q: q.state == "active")
            sections_with_active_q = active_q.mapped("page_id")

            survey.page_ids = survey.page_ids.filtered(
                lambda p: p in sections_with_active_q
            )
            survey.question_ids = active_q.filtered(
                lambda q: not q.page_id or q.page_id in sections_with_active_q
            )
            survey.question_count = len(survey.question_ids)
