pub mod metabolic;
pub mod longevity;
pub mod hormonal;
pub mod composite;

use super::unify::{BloodworkMarker, UserProfile};

/// Ergonomic lookup into a slice of BloodworkMarkers by canonical name.
pub struct MarkerLookup<'a> {
    markers: &'a [BloodworkMarker],
}

impl<'a> MarkerLookup<'a> {
    pub fn new(markers: &'a [BloodworkMarker]) -> Self {
        Self { markers }
    }

    /// Get a marker by canonical name (case-insensitive prefix match).
    pub fn get(&self, name: &str) -> Option<&'a BloodworkMarker> {
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
