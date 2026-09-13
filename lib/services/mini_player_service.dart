import 'package:PiliPlus/plugin/pl_player/controller.dart';
import 'package:PiliPlus/plugin/pl_player/models/play_status.dart';
import 'package:flutter/widgets.dart';
import 'package:get/get.dart';

final miniPlayerService = MiniPlayerService();
const appMiniPlayerRestoreKey = '_appMiniPlayerRestore';

class MiniPlayerSession {
  const MiniPlayerSession({
    required this.controller,
    required this.arguments,
    required this.heroTag,
    required this.title,
    this.active = false,
  });

  final PlPlayerController controller;
  final Map<String, dynamic> arguments;
  final String heroTag;
  final String title;
  final bool active;

  MiniPlayerSession copyWith({bool? active}) => MiniPlayerSession(
    controller: controller,
    arguments: arguments,
    heroTag: heroTag,
    title: title,
    active: active ?? this.active,
  );
}

class MiniPlayerService {
  MiniPlayerService() {
    PlPlayerController.onNewPlayerConsumer = _releaseForNewPlayer;
  }

  final Rxn<MiniPlayerSession> session = Rxn<MiniPlayerSession>();

  bool begin({
    required PlPlayerController controller,
    required Map arguments,
    required String heroTag,
    required String title,
  }) {
    if (controller.videoController == null ||
        !controller.playerStatus.isPlaying ||
        controller.isLive) {
      return false;
    }

    controller.isAppMiniPlayer = true;
    session.value = MiniPlayerSession(
      controller: controller,
      arguments: Map<String, dynamic>.from(arguments),
      heroTag: heroTag,
      title: title,
    );
    return true;
  }

  void activate(String heroTag) {
    final current = session.value;
    if (current == null || current.heroTag != heroTag) return;
    session.value = current.copyWith(active: true);
  }

  void restore() {
    final current = session.value;
    if (current == null || !current.active) return;

    // Remove the miniature surface before the detail page attaches a new one.
    session.value = current.copyWith(active: false);
    final arguments = Map<String, dynamic>.from(current.arguments)
      ..[appMiniPlayerRestoreKey] = true;
    Get.toNamed('/videoV', arguments: arguments);
  }

  void close() {
    final current = session.value;
    if (current == null) return;
    current.controller.isAppMiniPlayer = false;
    session.value = null;
    current.controller.dispose();
  }

  void _releaseForNewPlayer(PlPlayerController controller) {
    final current = session.value;
    if (current == null || !identical(current.controller, controller)) return;

    // A different video page opened while the miniature was visible. Pause
    // the old media; a restore hides the miniature before opening its page.
    if (current.active) {
      controller.pause();
    }
    controller.isAppMiniPlayer = false;

    // getInstance has just added the new page's reference. Release the
    // reference that was retained by the miniature player.
    PlPlayerController.updatePlayCount();

    // getInstance can be called while the destination video page is building.
    // Clearing the Rx session synchronously would mark the root Obx dirty in
    // the middle of that build and leave the restored page blank.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (identical(session.value, current)) {
        session.value = null;
      }
    });
    WidgetsBinding.instance.scheduleFrame();
  }
}
