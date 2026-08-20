"""Source- and layout-agnostic clinical document parsing.

Pipeline, each layer usable on its own:

    extract   bytes            -> Document (words + geometry)
    layout    Document         -> [Table]  (columns read off the page's header)
    classify  Document/Table   -> document type
    normalize Table            -> canonical records
    mappers   records          -> rows staged for a specific clinical table

`extract` and `layout` deliberately import nothing from the app, so they can be
exercised against a corpus of real PDFs without a database or settings.
"""
