{
    "name": "Plugins LSP Survey Extension",
    "version": "19.0.1.0.0",
    "author": "Muhammad Zaky Aliyashfi",
    "category": "Customizations/Survey",
    "depends": ["base", "survey", "plugins_manajement_asesor"],
    "data": [
        "security/ir.model.access.csv",
        "security/lsp_survey_rules.xml",
        "data/survey_seeder.xml",
        "views/survey_question_views_inherit.xml",
        "views/survey_templates_inherit.xml",
    ],
    "assets": {
        "survey.survey_assets": [
            "plugins_lsp_survey/static/src/css/survey_custom.css",
        ],
        "web.assets_backend": [
            "plugins_lsp_survey/static/src/js/question_page_list_renderer_patch.js",
            "plugins_lsp_survey/static/src/js/question_page_one2many_field_patch.js",
        ],
    },

    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
