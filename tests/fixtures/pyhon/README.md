# pyhOn archive fixture

`ac_1263/` is an anonymized hOn air-conditioner data archive, in the folder
format pyhOn's `TestAPI` reads. MAC addresses, serial codes and device
identifiers are replaced with `x`/`1` placeholders. It contains no account data.

The files are copied unchanged from `test_data/ac_1263` in
[Andre0512/hon-test-data](https://github.com/Andre0512/hon-test-data) at commit
`6098fc5dc2d42e1a0c71a3c1b673b937020603af`, which is licensed under the MIT
License. They are used only by `tests/test_pyhon_contract.py`.

Do not add archives made from your own account here: even an anonymized
archive can identify a household. Use public, already anonymized samples.
