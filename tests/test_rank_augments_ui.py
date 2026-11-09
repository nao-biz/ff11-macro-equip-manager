"""Rank abilities in production Tk details and comparison, using synthetic data."""
from dataclasses import replace
import os
import unittest

from ff11reader.rank_augments import RankCatalog, decode_bundles
from ff11reader.item_properties import ItemProperties
from tests.test_rank_augments import dat, item, FORMATS
from tests import test_equipment_review_ui as review
from tests.test_equipment_slots import SlotFixture
from tests.test_workspace_ui import WorkspaceMixin


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class RankAugmentUITests(WorkspaceMixin, SlotFixture):
    open_dense_view = review.EquipmentReviewUITests.open_dense_view

    def test_rank_values_in_inventory_and_equipment_panel(self):
        view = self.open_dense_view()
        slot = view.selected.slots[0]
        value = replace(item(), item_id=slot.item_id, index=slot.index)
        observation = view.augment_observations['abc']
        bags = tuple(replace(bag, items=tuple(value if bag.id == slot.container and old.index == slot.index else old
                                             for old in bag.items)) for bag in observation.export.bags)
        catalog = RankCatalog(decode_bundles(dat(((133, 0, tuple(range(31))),))), FORMATS)
        view.augment_observations['abc'] = replace(observation, export=replace(observation.export, bags=bags), rank_catalog=catalog)
        view.snapshot.items[slot.item_id]['description'] = '魔攻+35'
        before = self.editor.edit_status()
        view.change_mode(); view.inspect_slot(slot); self.app.update()
        labels = view.equipment_summary.metric_labels['魔攻', '']
        self.assertEqual(labels[2].cget('text'), '43')
        self.assertNotIn('取得日時', view.equipment_summary.extra_properties.get('1.0', 'end'))
        view.open_inventory(slot.container, slot.index); self.app.update()
        self.assertIn('魔攻+8', view.inventory_properties.contents()[1])
        self.assertIn('Rank 8', view.inventory_properties.identity.cget('text'))
        self.assertEqual(view.inventory_properties.contents()[1], '魔攻+8')
        view.inventory_properties.show(ItemProperties())
        self.app.update()
        self.assertEqual(self.editor.edit_status(), before)
