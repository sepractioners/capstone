import json

from extraction_agent.import_rag_dataset import import_dataset, normalize_record


def test_normalize_common_legal_dataset_fields() -> None:
    record = normalize_record({'id': 'ledgar-1', 'sentence': 'Confidentiality clause', 'label': 'confidentiality'}, 'ledgar', 0)
    assert record is not None
    assert record['id'] == 'ledgar-1'
    assert record['contract_type'] == 'confidentiality'
    assert record['dataset'] == 'ledgar'


def test_import_jsonl(tmp_path) -> None:
    source = tmp_path / 'contractnli.jsonl'
    source.write_text(json.dumps({'context': 'The agreement may terminate.'}) + '\n', encoding='utf-8')
    output = tmp_path / 'knowledge.jsonl'
    assert import_dataset(source, output, 'contractnli') == 1
    assert 'contractnli:0' in output.read_text(encoding='utf-8')
