pub mod metabolic;
pub mod longevity;
pub mod hormonal;
pub mod composite;

use super::unify::{HepatologyMarker, UserProfile};

/// Ergonomic lookup into a slice of HepatologyMarkers by canonical name.
pub struct MarkerLookup<'a> {
    markers: &'a [HepatologyMarker],
}

impl<'a> MarkerLookup<'a> {
    pub fn new(markers: &'a [HepatologyMarker]) -> Self {
        Self { markers }
    }

    /// Get a marker by canonical name (case-insensitive prefix match).
    pub fn get(&self, name: &str) -> Option<&'a HepatologyMarker> {
        let lower = name.to_lowercase();
        self.markers
            .iter()
            .find(|m| m.name.to_lowercase().starts_with(&lower))
    }

    /// Get a marker's value by canonical name.
    pub fn val(&self, name: &str) -> Option<f64> {
        self.get(name).map(|m| m.value)
    }
}
