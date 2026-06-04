{
    "name": "Plugins LSP Survey Extension",
    "version": "19.0.1.0.0",
    "author": "Muhammad Zaky Aliyashfi",
    "category": "Customizations/Survey",
    "depends": ["base", "survey", "plugins_manajement_asesor"],
    "data": [
        "security/ir.model.access.csv",
        "views/survey_question_views_inherit.xml",
        "views/survey_templates_inherit.xml",
    ],
    "assets": {
        "survey.survey_assets": [
            "plugins_lsp_survey/static/src/css/survey_custom.css",
        ],
    },

    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
