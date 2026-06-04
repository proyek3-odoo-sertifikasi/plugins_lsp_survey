from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class SurveyQuestion(models.Model):
    _inherit = "survey.question"

    # Field untuk Section (is_page=True) yang merepresentasikan Unit Kompetensi
    # - title  (bawaan Odoo) = Nama Unit Kompetensi
    # - unit_code (tambahan) = Kode Unit Kompetensi
    unit_code = fields.Char(string="Kode Unit", help="Kode unit kompetensi, contoh: TIK.PR01.001.01")
    lsp_question_type = fields.Selection([
        ('pg', 'Pilihan Ganda'),
        ('essay', 'Esai'),
        ('praktikum', 'Praktikum')
    ], string="Tipe Soal LSP", default='pg', required=True)

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

    @api.model_create_multi
    def create(self, vals_list):
        """Hanya LSP Asesor yang boleh membuat soal atau section baru.

        LSP Admin dapat membaca, meng-approve, dan merevisi soal,
        tetapi TIDAK dapat membuat soal baru — itu adalah hak eksklusif Asesor.
        Context flag ``lsp_allow_non_asesor_create`` dapat dipakai oleh
        kode internal (mis. impor data) untuk melewati pembatasan ini.
        """
        if not self.env.context.get("lsp_allow_non_asesor_create") and not self.env.user.has_group(
            "plugins_manajement_asesor.group_asesor"
        ):
            raise AccessError(
                _(
                    "Hanya user dengan role LSP Asesor yang boleh membuat soal atau section. "
                    "LSP Admin hanya dapat menyetujui atau merevisi soal yang sudah dibuat."
                )
            )
        return super().create(vals_list)

    def action_submit(self):
        if not self.env.user.has_group("plugins_manajement_asesor.group_asesor"):
            raise AccessError(_("Hanya LSP Asesor yang bisa mengajukan validasi soal."))
        if any(question.state not in ("draft", "revise") for question in self):
            raise UserError(_("Status hanya bisa diajukan dari Draft or Revise."))
        self.write({"state": "waiting"})
        return True

    def action_approve(self):
        """Setujui soal/section → ubah status menjadi Active.

        LSP Admin dapat menyetujui soal dari status Draft, Waiting, maupun Revise.
        Soal yang sudah Active tidak perlu disetujui ulang.
        """
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


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    def _lsp_filter_active_questions(self, questions):
        """Keep only approved questions and their parent sections for the participant-facing flow.

        Rules:
        - A SECTION (is_page=True) is shown if it has >=1 active question inside it.
          The section itself does NOT need to be 'active'.
        - A QUESTION (is_page=False) is shown only if state == 'active'.

        Important: when questions_layout == 'page_per_section', Odoo passes only the
        section records to this method. In that case we must look up the active
        questions from the survey's full question_and_page_ids, not from the passed list.
        """
        if self.env.context.get("lsp_include_inactive_questions"):
            return questions

        has_pages = any(q.is_page for q in questions)
        has_non_pages = any(not q.is_page for q in questions)

        if has_pages and not has_non_pages:
            # page_per_section layout: only sections were passed.
            # Determine which sections have at least one active question
            # by looking at the full survey question list.
            all_non_page = self.question_and_page_ids.filtered(lambda q: not q.is_page)
            active_non_page = all_non_page.filtered(lambda q: q.state == "active")
            sections_with_active_q = active_non_page.mapped("page_id")
            return questions.filtered(lambda p: p in sections_with_active_q)

        # Mixed or questions-only input (page_per_question / one_page layout)
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
        """Override untuk mencegah ValueError saat navigasi survey.

        Jika survey tidak memiliki soal/section yang aktif, atau jika ID soal yang diminta
        tidak ada dalam daftar soal aktif (misal karena berstatus draft/waiting/revise),
        metode ini akan mengembalikan recordset kosong secara aman daripada menyebabkan crash.
        """
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
        """Override to expose only sections-with-active-questions and active questions.

        This makes survey validity checks (survey_void detection) and the progression
        bar work correctly with the LSP active-question filter.
        """
        super()._compute_page_and_question_ids()

        if self.env.context.get("lsp_include_inactive_questions"):
            return

        for survey in self:
            # Active (non-page) questions whose parent section also has >=1 active question
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


