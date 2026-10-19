"""Archive integrity tests, using only tiny synthetic package trees."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from scripts.release_archive import build_archive,extract_verified


class ReleaseArchiveTests(unittest.TestCase):
    def test_both_formats_extract_complete_resources_and_exact_commit(self):
        for suffix in ('.zip','.tar.gz'):
            with self.subTest(suffix=suffix), TemporaryDirectory() as temp:
                root=Path(temp);bundle=root/'DCA-Monitor';bundle.mkdir()
                (bundle/'program').write_bytes(b'SYNTHETIC EXECUTABLE FIXTURE')
                (bundle/'resource.txt').write_bytes(b'visual resource')
                target=root/('app'+suffix)
                build_archive(bundle,target,commit='a'*40)
                extracted,manifest=extract_verified(target,root/'fresh',commit='a'*40)
                self.assertEqual(manifest['commit'],'a'*40)
                self.assertEqual((extracted/'resource.txt').read_bytes(),b'visual resource')
                with self.assertRaises(FileExistsError):extract_verified(target,root/'fresh')
                with self.assertRaisesRegex(ValueError,'Identidade'):
                    extract_verified(target,root/'wrong',commit='b'*40)

    def test_financial_or_preview_files_are_never_packaged(self):
        for name in ('original.csv','portfolio.sqlite3','DCA-PREVIEW-MODE'):
            with self.subTest(name=name),TemporaryDirectory() as temp:
                root=Path(temp);bundle=root/'DCA-Monitor';bundle.mkdir()
                (bundle/name).write_bytes(b'forbidden synthetic fixture')
                with self.assertRaisesRegex(ValueError,'não permitido'):
                    build_archive(bundle,root/'test.zip',commit='a'*40)
                self.assertFalse((root/'test.zip').exists())

    def test_tampered_or_traversal_archive_is_rejected(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);bundle=root/'DCA-Monitor';bundle.mkdir()
            (bundle/'program').write_bytes(b'original')
            target=root/'test.zip';build_archive(bundle,target,commit='a'*40)
            with zipfile.ZipFile(target) as source:
                files={n:source.read(n) for n in source.namelist()}
            with zipfile.ZipFile(target,'w') as output:
                for name,body in files.items():
                    output.writestr(name,b'tampered' if name.endswith('/program') else body)
            with self.assertRaisesRegex(ValueError,'Hash divergente'):
                extract_verified(target,root/'bad')
            with zipfile.ZipFile(root/'escape.zip','w') as output:
                output.writestr('DCA-Monitor/../../escaped','bad')
            with self.assertRaisesRegex(ValueError,'Caminho inválido'):
                extract_verified(root/'escape.zip',root/'escape')
            self.assertFalse((root/'escaped').exists())


if __name__=='__main__':unittest.main()
