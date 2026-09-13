import 'dart:io' show Platform;
import 'dart:math' as math;

import 'package:PiliPlus/services/mini_player_service.dart';
import 'package:PiliPlus/plugin/pl_player/models/play_status.dart';
import 'package:PiliPlus/utils/android/bindings.g.dart';
import 'package:get/get.dart';
import 'package:material_ui/material_ui.dart';
import 'package:media_kit_video/media_kit_video.dart';

class AppMiniPlayer extends StatelessWidget {
  const AppMiniPlayer({super.key});

  @override
  Widget build(BuildContext context) => Obx(() {
    final session = miniPlayerService.session.value;
    final controller = session?.controller;
    final videoController = controller?.videoController;
    if (session == null ||
        !session.active ||
        controller == null ||
        videoController == null) {
      return const SizedBox.shrink();
    }

    final isSystemPip = Platform.isAndroid && AndroidHelper.isPipMode;
    final video = ColoredBox(
      color: Colors.black,
      child: FittedBox(
        fit: controller.videoFit.value.boxFit,
        child: SimpleVideo(
          controller: videoController,
          fill: Colors.black,
          aspectRatio: controller.videoFit.value.aspectRatio,
        ),
      ),
    );

    if (isSystemPip) {
      return Positioned.fill(child: video);
    }

    final mediaQuery = MediaQuery.of(context);
    final screenSize = mediaQuery.size;
    final width = math.min(220.0, screenSize.width * 0.54);
    final bottom = screenSize.height >= screenSize.width
        ? mediaQuery.padding.bottom + 80
        : mediaQuery.padding.bottom + 12;

    return Positioned(
      right: 12,
      bottom: bottom,
      width: width,
      child: Semantics(
        container: true,
        explicitChildNodes: true,
        label: '应用内小窗：${session.title}',
        button: true,
        onTap: miniPlayerService.restore,
        child: Material(
          elevation: 10,
          color: Colors.black,
          clipBehavior: Clip.antiAlias,
          borderRadius: const BorderRadius.all(Radius.circular(10)),
          child: AspectRatio(
            aspectRatio: 16 / 9,
            child: Stack(
              fit: StackFit.expand,
              children: [
                video,
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: miniPlayerService.restore,
                ),
                Align(
                  alignment: Alignment.center,
                  child: Obx(() {
                    final isPlaying = controller.playerStatus.isPlaying;
                    final onPressed = isPlaying
                        ? controller.pause
                        : controller.play;
                    return Semantics(
                      label: isPlaying ? '暂停' : '继续播放',
                      button: true,
                      onTap: onPressed,
                      child: ExcludeSemantics(
                        child: IconButton.filledTonal(
                          style: IconButton.styleFrom(
                            backgroundColor: Colors.black54,
                            foregroundColor: Colors.white,
                          ),
                          onPressed: onPressed,
                          icon: Icon(
                            isPlaying
                                ? Icons.pause_rounded
                                : Icons.play_arrow_rounded,
                          ),
                        ),
                      ),
                    );
                  }),
                ),
                Align(
                  alignment: Alignment.topRight,
                  child: Semantics(
                    label: '关闭小窗',
                    button: true,
                    onTap: miniPlayerService.close,
                    child: ExcludeSemantics(
                      child: IconButton(
                        style: IconButton.styleFrom(
                          backgroundColor: Colors.black54,
                          foregroundColor: Colors.white,
                          minimumSize: const Size.square(32),
                          padding: EdgeInsets.zero,
                        ),
                        onPressed: miniPlayerService.close,
                        icon: const Icon(Icons.close_rounded, size: 20),
                      ),
                    ),
                  ),
                ),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Obx(() {
                    final duration = controller.duration.value;
                    final value = duration <= 0
                        ? null
                        : (controller.position.value / duration)
                              .clamp(0.0, 1.0)
                              .toDouble();
                    return LinearProgressIndicator(
                      value: value,
                      minHeight: 2,
                      backgroundColor: Colors.white24,
                      color: Theme.of(context).colorScheme.primary,
                    );
                  }),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  });
}
