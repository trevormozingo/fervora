import { useState, useEffect } from 'react';
import { ActivityIndicator, Alert, Modal, Pressable, StyleSheet, View } from 'react-native';
import MapView, { Marker, Region } from 'react-native-maps';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { Text, colors, spacing, radii } from '@/components/ui';

type LocationResult = {
  coordinates: [number, number]; // [lng, lat]
  label: string | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  onSelect: (location: LocationResult) => void;
  /** Initial coordinates [lng, lat] to center the map on */
  initialCoords?: [number, number] | null;
};

const DEFAULT_REGION: Region = {
  latitude: 37.7749,
  longitude: -122.4194,
  latitudeDelta: 0.05,
  longitudeDelta: 0.05,
};

export function LocationPicker({ visible, onClose, onSelect, initialCoords }: Props) {
  const [region, setRegion] = useState<Region>(
    initialCoords
      ? { latitude: initialCoords[1], longitude: initialCoords[0], latitudeDelta: 0.05, longitudeDelta: 0.05 }
      : DEFAULT_REGION
  );
  const [pin, setPin] = useState<{ latitude: number; longitude: number }>(
    initialCoords
      ? { latitude: initialCoords[1], longitude: initialCoords[0] }
      : { latitude: DEFAULT_REGION.latitude, longitude: DEFAULT_REGION.longitude }
  );
  const [locating, setLocating] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Center map on user's location when opened (if no initial coords)
  useEffect(() => {
    if (!visible) return;
    if (initialCoords) {
      const r = { latitude: initialCoords[1], longitude: initialCoords[0], latitudeDelta: 0.05, longitudeDelta: 0.05 };
      setRegion(r);
      setPin({ latitude: initialCoords[1], longitude: initialCoords[0] });
      return;
    }
    (async () => {
      try {
        setLocating(true);
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== 'granted') return;
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        const r = { latitude: pos.coords.latitude, longitude: pos.coords.longitude, latitudeDelta: 0.05, longitudeDelta: 0.05 };
        setRegion(r);
        setPin({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
      } catch {
        // stay on default
      } finally {
        setLocating(false);
      }
    })();
  }, [visible, initialCoords]);

  const goToMyLocation = async () => {
    try {
      setLocating(true);
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Enable location permissions in Settings.');
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const r = { latitude: pos.coords.latitude, longitude: pos.coords.longitude, latitudeDelta: 0.05, longitudeDelta: 0.05 };
      setRegion(r);
      setPin({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not get location');
    } finally {
      setLocating(false);
    }
  };

  const handleConfirm = async () => {
    try {
      setConfirming(true);
      // Reverse geocode the pin position
      const [geo] = await Location.reverseGeocodeAsync({ latitude: pin.latitude, longitude: pin.longitude });
      const label = geo ? [geo.city, geo.region].filter(Boolean).join(', ') : null;
      onSelect({
        coordinates: [pin.longitude, pin.latitude],
        label,
      });
    } catch {
      onSelect({
        coordinates: [pin.longitude, pin.latitude],
        label: null,
      });
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <Pressable onPress={onClose} hitSlop={12}>
            <Ionicons name="close" size={24} color={colors.foreground} />
          </Pressable>
          <Text style={styles.title}>Choose Location</Text>
          <View style={{ width: 24 }} />
        </View>

        <Text muted style={styles.hint}>Tap the map to drop a pin, then confirm.</Text>

        {/* Map */}
        <View style={styles.mapContainer}>
          <MapView
            style={styles.map}
            region={region}
            onRegionChangeComplete={setRegion}
            onPress={(e) => setPin(e.nativeEvent.coordinate)}
            showsUserLocation
            showsMyLocationButton={false}
          >
            <Marker
              coordinate={pin}
              draggable
              onDragEnd={(e) => setPin(e.nativeEvent.coordinate)}
            />
          </MapView>

          {/* My Location FAB */}
          <Pressable style={styles.myLocationFab} onPress={goToMyLocation} disabled={locating}>
            {locating ? (
              <ActivityIndicator size="small" color={colors.primary} />
            ) : (
              <Ionicons name="navigate" size={20} color={colors.primary} />
            )}
          </Pressable>
        </View>

        {/* Confirm button */}
        <View style={styles.footer}>
          <Pressable style={styles.confirmButton} onPress={handleConfirm} disabled={confirming}>
            {confirming ? (
              <ActivityIndicator size="small" color={colors.primaryForeground} />
            ) : (
              <Text style={styles.confirmText}>Confirm Location</Text>
            )}
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: 56,
    paddingBottom: spacing.sm,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  hint: {
    textAlign: 'center',
    fontSize: 13,
    marginBottom: spacing.sm,
  },
  mapContainer: {
    flex: 1,
    position: 'relative',
  },
  map: {
    flex: 1,
  },
  myLocationFab: {
    position: 'absolute',
    bottom: 16,
    right: 16,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 4,
  },
  footer: {
    padding: spacing.lg,
    paddingBottom: 40,
  },
  confirmButton: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: radii.sm,
    alignItems: 'center',
  },
  confirmText: {
    color: colors.primaryForeground,
    fontWeight: '700',
    fontSize: 16,
  },
});
