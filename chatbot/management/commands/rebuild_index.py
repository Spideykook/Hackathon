"""
chatbot/management/commands/rebuild_index.py

Usage:
    python manage.py rebuild_index              # rebuild both
    python manage.py rebuild_index --products   # products only
    python manage.py rebuild_index --support    # support only
"""

from django.core.management.base import BaseCommand
from chatbot.indexing import IndexManager


class Command(BaseCommand):
    help = "Rebuild FAISS vector indices for products and/or support documents."

    def add_arguments(self, parser):
        parser.add_argument("--products", action="store_true", help="Rebuild product index only")
        parser.add_argument("--support", action="store_true", help="Rebuild support index only")

    def handle(self, *args, **options):
        mgr = IndexManager()
        products_only = options["products"]
        support_only = options["support"]

        if not products_only and not support_only:
            self.stdout.write("Rebuilding all indices...")
            mgr.rebuild_all()
        elif products_only:
            self.stdout.write("Rebuilding product index...")
            mgr.rebuild_products()
        elif support_only:
            self.stdout.write("Rebuilding support index...")
            mgr.rebuild_support()

        self.stdout.write(self.style.SUCCESS("Done."))
