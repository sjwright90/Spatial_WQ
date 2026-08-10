import unittest

from app.src.data_model import ColumnMapping, ColumnRole, ROLE_REGISTRY


class TestRoleRegistry(unittest.TestCase):
    def test_registry_covers_every_role(self):
        registered_roles = {spec.role for spec in ROLE_REGISTRY}
        self.assertEqual(registered_roles, set(ColumnRole))

    def test_required_roles(self):
        required = {spec.role for spec in ROLE_REGISTRY if spec.required}
        self.assertEqual(
            required,
            {
                ColumnRole.LOCATION_ID,
                ColumnRole.LATITUDE,
                ColumnRole.LONGITUDE,
                ColumnRole.PLOTTING_GROUP,
            },
        )

    def test_multi_roles(self):
        multi = {spec.role for spec in ROLE_REGISTRY if spec.multi}
        self.assertEqual(
            multi,
            {
                ColumnRole.NUMERIC_SIMPLE,
                ColumnRole.NUMERIC_CLR,
                ColumnRole.PLOTTING_GROUP,
                ColumnRole.GROUP_COLOR,
            },
        )


class TestColumnMapping(unittest.TestCase):
    def test_defaults(self):
        mapping = ColumnMapping(location_id="Site", latitude="lat", longitude="lon")
        self.assertEqual(mapping.plotting_groups, [])
        self.assertEqual(mapping.numeric_simple, [])
        self.assertEqual(mapping.numeric_clr, [])
        self.assertIsNone(mapping.date)
        self.assertIsNone(mapping.marker_symbol)
        self.assertIsNone(mapping.map_marker_size)
        self.assertEqual(mapping.group_colors, {})

    def test_all_mapped_columns(self):
        mapping = ColumnMapping(
            location_id="Site",
            latitude="lat",
            longitude="lon",
            plotting_groups=["Group1"],
            numeric_simple=["Cu"],
            numeric_clr=["Zn"],
            date="SampleDate",
            marker_symbol="Marker",
            map_marker_size="Size",
            group_colors={"Group1": "Group1Color"},
        )
        cols = mapping.all_mapped_columns()
        self.assertEqual(
            set(cols),
            {
                "Site",
                "lat",
                "lon",
                "Group1",
                "Cu",
                "Zn",
                "SampleDate",
                "Marker",
                "Size",
                "Group1Color",
            },
        )

    def test_all_mapped_columns_minimal(self):
        mapping = ColumnMapping(location_id="Site", latitude="lat", longitude="lon")
        self.assertEqual(mapping.all_mapped_columns(), ["Site", "lat", "lon"])


if __name__ == "__main__":
    unittest.main()
