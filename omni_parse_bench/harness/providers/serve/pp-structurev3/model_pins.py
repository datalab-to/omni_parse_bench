"""The Hugging Face models PPStructureV3() loads at its defaults, each at an exact commit.

PaddleX's Hugging Face source downloads the latest of a model (`snapshot_download` with no revision), so the
image puts these commits where PaddleX looks first (`pin_models.py`), and PaddleX finds them there and
downloads nothing. The list is the 13 models the pipeline created on a first run (its defaults: layout,
region, orientation, unwarping, OCR, table and formula models); the commits are each repository's head on
2026-11-25.
"""
MODELS = {
    "PP-DocLayout_plus-L": "aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d",
    "PP-DocBlockLayout": "f270657da59d956ab69ffc2c4722fe1f557bf17b",
    "PP-OCRv5_server_det": "ca867c897ecbca8873081573a802ad70d499cb94",
    "PP-OCRv5_server_rec": "b26c3587fda8da3c8ec0ce357214b4d661ff1558",
    "PP-LCNet_x1_0_doc_ori": "d3b95a6dff5fe8a94f2748e12b61cb26818a0df8",
    "PP-LCNet_x1_0_textline_ori": "cd237a44b0e359d4fe38310a416203cf7403faa5",
    "PP-LCNet_x1_0_table_cls": "2fa6323e7dab88fa883081db1460995f46af2922",
    "UVDoc": "16c3f0ea9c2f0c6a57e24160f7eeaa7574613fa3",
    "SLANet_plus": "bae6e5f8c3c4e7da0c0b7639fdf3228fe76184e2",
    "SLANeXt_wired": "763069fcda6a065f2171753205a32bf899a88d15",
    "RT-DETR-L_wired_table_cell_det": "e2bd53c06b3a815d86acbf5c6779dada58819cfe",
    "RT-DETR-L_wireless_table_cell_det": "25ca86356a601c877476bb0dcc5fd09153d9d64d",
    "PP-FormulaNet_plus-L": "0809597a77f735bfb35354edb632f2e6dff606f3",
}
