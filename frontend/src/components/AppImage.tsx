import { Platform, Image as RNImage } from "react-native";
import { Image as ExpoImage, type ImageProps as ExpoImageProps } from "expo-image";

// expo-image has no Windows view manager (see react-native.config.js /
// CLAUDE.md "Known remaining gaps") -- renders as a red "Unimplemented
// component" placeholder there. Falls back to react-native's built-in Image
// on Windows, translating the (small) subset of props this app actually uses.
export function AppImage(props: ExpoImageProps) {
  if (Platform.OS === "windows") {
    const { source, style, contentFit, testID } = props;
    return (
      <RNImage
        source={source as any}
        style={style as any}
        resizeMode={contentFit === "cover" ? "cover" : "contain"}
        testID={testID}
      />
    );
  }
  return <ExpoImage {...props} />;
}
