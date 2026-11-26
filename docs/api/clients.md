# Clients

`Client` and `AsyncClient` share the same interface: every method that talks to the API
is a coroutine on `AsyncClient`.


::: jaquette.clients
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_root_full_path: false
      show_root_members_full_path: false
      show_object_full_path: false
      show_labels: false
      show_symbol_type_heading: false
      separate_signature: false
      show_signature_annotations: true
      members:
        - DEFAULT_BASE_URL
        - DEFAULT_TIMEOUT
        - DEFAULT_MAX_RETRIES


::: jaquette.Client
    options:
      members:
        - get_product
        - search
        - close


::: jaquette.AsyncClient
    options:
      members:
        - get_product
        - search
        - aclose
