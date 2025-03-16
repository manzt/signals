# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import enum
import typing
from typing import cast


class SubscriberFlags(enum.IntFlag):
    Computed = 1 << 0
    Effect = 1 << 1
    Tracking = 1 << 2
    Notified = 1 << 3
    Recursed = 1 << 4
    Dirty = 1 << 5
    PendingComputed = 1 << 6
    PendingEffect = 1 << 7
    Propagated = Dirty | PendingComputed | PendingEffect


class Link:  # noqa: B903
    def __init__(
        self,
        dep: Dependency | DependencyWithSubscriber,
        sub: Subscriber | DependencyWithSubscriber,
        prev_sub: Link | None,
        next_sub: Link | None,
        next_dep: Link | None,
    ) -> None:
        self.dep = dep
        self.sub = sub
        self.prev_sub = prev_sub
        self.next_sub = next_sub
        self.next_dep = next_dep


class Dependency(typing.Protocol):
    subs: Link | None
    subs_tail: Link | None


class Subscriber(typing.Protocol):
    flags: SubscriberFlags
    deps: Link | None
    deps_tail: Link | None


class DependencyWithSubscriber(Dependency, Subscriber): ...


class UpdateComputed(typing.Protocol):
    def __call__(self, computed: DependencyWithSubscriber) -> bool:
        """Update the computed subscriber's value and returns whether it changed.

        This function should be called when a computed subscriber is marked as Dirty.
        The computed subscriber's getter function is invoked, and its value is updated.
        If the value changes, the new value is stored, and the function returns `true`.

        Parameters
        ----------
        computed : DependencyWithSubscriber
            The computed subscriber to update.

        Returns
        -------
        bool
            Whether the computed subscriber's value changed
        """
        ...


class NotifyEffect(typing.Protocol):
    def __call__(self, effect: Subscriber) -> bool:
        """Handle notifications by processing the specified `effect`.

        When an `effect` first receives any of the following flags:

        - `Dirty`
        - `PendingComputed`
        - `PendingEffect`

        this method processes them and return `True` if the successfully handled.
        If not fully handled, future changes to these flags will trigger additional
        calls until the method eventually returns `True`.

        Parameters
        ----------
        effect : Subscriber
            The effect subscriber

        Returns
        -------
        bool
            Whether the flags are successfully handled.
        """
        ...


class ReactiveSystem:
    def __init__(
        self,
        update_computed: UpdateComputed,
        notify_effect: NotifyEffect,
    ) -> None:
        self.update_computed = update_computed
        self.notify_effect = notify_effect
        self.queued_effects: Subscriber | None = None
        self.queued_effects_tail: Subscriber | None = None

    def link(self, dep: Dependency, sub: Subscriber) -> Link | None:  # noqa: PLR6301
        """Link a given dependency and subscriber if they are not already linked.

        Parameters
        ----------
        dep : Dependency
            The dependency to be linked.

        sub : Subscriber
            The subscriber that depends on this dependency.

        Returns
        -------
        Link | None
            A newly created `Link` if the two are not already linked; otherwise `None`.
        """
        current_dep = sub.deps_tail
        if current_dep and current_dep.dep == dep:
            return None
        next_dep = current_dep.next_dep if current_dep else sub.deps
        if next_dep and next_dep.dep == dep:
            sub.deps_tail = next_dep
            return None
        dep_last_sub = dep.subs_tail
        if (
            dep_last_sub
            and dep_last_sub.sub == sub
            and is_valid_link(dep_last_sub, sub)
        ):
            return None

        return link_new_dep(dep, sub, next_dep, current_dep)

    def propagate(self, link: Link) -> None:  # noqa: C901, PLR0912
        """Traverse and mark subscribers starting from the provided link.

        Sets flags (e.g., Dirty, PendingComputed, PendingEffect) on each subscriber
        to indicate which ones require re-computation or effect processing.

        This function should be called after a signal's value changes.

        Parameters
        ----------
        link : Link
            The starting link from which propagation begins.
        """
        target_flag = SubscriberFlags.Dirty
        subs = link
        stack = 0

        while True:
            sub = link.sub
            sub_flags = sub.flags
            # fmt: off
            if (  # noqa: PLR0916
                not (sub_flags & (SubscriberFlags.Tracking | SubscriberFlags.Recursed | SubscriberFlags.Propagated))  # noqa: E501
                and set_flags(sub, sub_flags | target_flag | SubscriberFlags.Notified)
            ) or (
                (sub_flags & SubscriberFlags.Recursed)
                and not (sub_flags & SubscriberFlags.Tracking)
                and set_flags(sub, (sub_flags & ~SubscriberFlags.Recursed) | target_flag | SubscriberFlags.Notified)  # noqa: E501
            ) or (
                not (sub_flags & SubscriberFlags.Propagated)
                and is_valid_link(link, sub)
                and set_flags(sub, sub_flags | SubscriberFlags.Recursed | target_flag | SubscriberFlags.Notified)  # noqa: E501
                and hasattr(sub, "subs")
            ):
                # fmt: on
                sub_subs: Link | None = getattr(sub, "subs", None)
                if sub_subs:
                    if sub_subs.next_sub:
                        sub_subs.prev_sub = subs
                        link = subs = sub_subs
                        target_flag = SubscriberFlags.PendingComputed
                        stack += 1
                    else:
                        link = sub_subs
                        target_flag = (
                            SubscriberFlags.PendingEffect
                            if sub_flags & SubscriberFlags.Effect
                            else SubscriberFlags.PendingComputed
                        )
                    continue
                if sub_flags & SubscriberFlags.Effect:
                    if self.queued_effects_tail:
                        cast("Link", self.queued_effects_tail.deps_tail).next_dep = sub.deps  # noqa: E501
                    else:
                        self.queued_effects = sub
                    self.queued_effects_tail = sub

            elif not (sub_flags & (SubscriberFlags.Tracking | target_flag)):
                sub.flags = sub_flags | target_flag | SubscriberFlags.Notified
                if (sub_flags & (SubscriberFlags.Effect | SubscriberFlags.Notified)) == SubscriberFlags.Effect:  # noqa: E501
                    if self.queued_effects_tail:
                        cast("Link", self.queued_effects_tail.deps_tail).next_dep = sub.deps  # noqa: E501
                    else:
                        self.queued_effects = sub
                    self.queued_effects_tail = sub

            elif (
                not (sub_flags & target_flag)
                and (sub_flags & SubscriberFlags.Propagated)
                and is_valid_link(link, sub)
            ):
                sub.flags = sub_flags | target_flag

            if (link := cast("Link", subs.next_sub)):
                subs = link
                target_flag = (
                    SubscriberFlags.PendingComputed if stack else SubscriberFlags.Dirty
                )
                continue

            while stack:
                stack -= 1
                dep = subs.dep
                dep_subs = cast("Link", dep.subs)
                subs = cast("Link", dep_subs.prev_sub)
                dep_subs.prev_sub = None
                if (link := cast("Link", subs.next_sub)):
                    subs = link
                    target_flag = (
                        SubscriberFlags.PendingComputed
                        if stack
                        else SubscriberFlags.Dirty
                    )
                    break  # Ensures we exit while stack and go back to the outer loop
            else:
                break  # Fully exit both loops if stack is empty

    def start_tracking(self, sub: Subscriber) -> None:  # noqa: PLR6301
        """Prepare the given subscriber to track new dependencies.

        Resets the subscriber's internal pointers (i.e., deps_tail) and
        sets its flags to indicate it is now tracking dependency links.

        Parameters
        ----------
        sub : Subscriber
            The subscriber to start tracking.
        """
        sub.deps_tail = None
        sub.flags = (
            sub.flags
            & ~(
                SubscriberFlags.Notified
                | SubscriberFlags.Recursed
                | SubscriberFlags.Propagated
            )
        ) | SubscriberFlags.Tracking

    def end_tracking(self, sub: Subscriber) -> None:  # noqa: PLR6301
        """Conclude tracking of dependencies for the specified subscriber.

        Clears or unlinks any tracked dependency information, then
        updates the subscriber's flags to indicate tracking is complete.

        Parameters
        ----------
        sub : Subscriber
            The subscriber whose tracking is ending.

        """
        deps_tail = sub.deps_tail
        if deps_tail:
            next_dep = deps_tail.next_dep
            if next_dep:
                clear_tracking(next_dep)
                deps_tail.next_dep = None
        elif sub.deps:
            clear_tracking(sub.deps)
            sub.deps = None
        sub.flags &= ~SubscriberFlags.Tracking

    def update_dirty_flag(self, sub: Subscriber, flags: SubscriberFlags) -> bool:
        """Update the dirty flag for the given subscriber based on its dependencies.

        If the subscriber has any computed, sets the DirtyFalg and returns `True`.
        Otherwise, clears the PendingComputed flag and returns `False`.

        Parameters
        ----------
        sub : Subscriber
            The subscriber to update.
        flags: SubscriberFlags
            The current flag set for this subscriber.

        Returns
        -------
        bool
            Whether the subscriber is marked as Dirty.
        """
        if sub.deps and self._check_dirty(sub.deps):
            sub.flags = flags | SubscriberFlags.Dirty
            return True
        sub.flags = flags & ~SubscriberFlags.PendingComputed
        return False

    def process_computed_update(
        self,
        computed: DependencyWithSubscriber,
        flags: SubscriberFlags,
    ) -> None:
        """Update the computed subscriber if necessary before its value is accessed.

        If the subscriber is marked Dirty or PendingComputed, this function runs
        the provided update_computed logic and triggers a shallowPropagate for any
        downstream subscribers if an actual update occurs.

        Parameters
        ----------
        computed : DependencyWithSubscriber
            The computed subscriber to update.
        flags : SubscriberFlags
            The current flag set for this subscriber.
        """
        if (
            flags & SubscriberFlags.Dirty
            or (
                True
                if computed.deps and self._check_dirty(computed.deps)
                else (
                    set_flags(computed, flags & ~SubscriberFlags.PendingComputed)
                    and False
                )
            )
        ) and self.update_computed(computed):
            subs = computed.subs
            if subs:
                self._shallow_propagate(subs)

    def process_pending_inner_effects(
        self,
        sub: Subscriber,
        flags: SubscriberFlags,
    ) -> None:
        """Ensure all pending internal effects for the given subscriber are processed.

        Should be called after an effect decides not to re-run itself but may still
        have dependencies flagged with PendingEffect. If the subscriber is flagged
        with PendingEffect, this function clears that flag and invokes `notify_effect`
        on any related dependencies marked as Effect and Propagated, processing
        pending effects.

        Parameters  # noqa: PLR6301
        ----------
        sub : Subscriber
            The subscriber which may have pending effects.
        flags : SubscriberFlags
            The current flags on the subscriber to check.
        """
        if flags & SubscriberFlags.PendingEffect:
            sub.flags = flags & ~SubscriberFlags.PendingEffect
            link = sub.deps
            while link:
                dep = link.dep
                if (
                    hasattr(dep, "flags")
                    and cast("Subscriber", dep).flags & SubscriberFlags.Effect
                    and cast("Subscriber", dep).flags & SubscriberFlags.Propagated
                ):
                    self.notify_effect(cast("Subscriber", dep))
                link = link.next_dep

    def process_effect_notifications(self) -> None:
        """Process queued effect notifications after a batch operation finishes.

        Iterates through all queued effects, calling notifyEffect on each.
        If an effect remains partially handled, its flags are updated, and future
        notifications may be triggered until fully handled.
        """
        while self.queued_effects:
            effect = self.queued_effects
            deps_tail = cast("Link", effect.deps_tail)
            queued_next = deps_tail.next_dep
            if queued_next:
                deps_tail.next_dep = None
                self.queued_effects = queued_next.sub
            else:
                self.queued_effects = None
                self.queued_effects_tail = None

            if not self.notify_effect(effect):
                effect.flags &= ~SubscriberFlags.Notified

    def _check_dirty(self, link: Link) -> bool:  # noqa: C901, PLR0912, PLR0915
        """Recursively check and update all computed subscribers marked as pending.

        Traverses the linked structure using a stack mechanism. For each computed
        subscriber in a pending state, calls update_computed and shallow_propagate
        if a value changes.


        Parameters
        ----------
        link : Link
            The starting link representing a sequence of pending computeds.

        Returns
        -------
        bool
            Whether any updates occurred.
        """
        stack = 0
        dirty = False

        while True:  # noqa: PLR1702
            dirty = False
            dep = link.dep

            if hasattr(dep, "flags"):
                dep_flags = cast("DependencyWithSubscriber", dep).flags
                if (dep_flags & (SubscriberFlags.Computed | SubscriberFlags.Dirty)) == (
                    SubscriberFlags.Computed | SubscriberFlags.Dirty
                ):
                    if self.update_computed(cast("DependencyWithSubscriber", dep)):
                        subs = dep.subs
                        if subs and subs.next_sub:
                            self._shallow_propagate(subs)
                        dirty = True
                elif (
                    dep_flags
                    & (SubscriberFlags.Computed | SubscriberFlags.PendingComputed)
                ) == (SubscriberFlags.Computed | SubscriberFlags.PendingComputed):
                    dep_subs = dep.subs
                    if dep_subs and dep_subs.next_sub:
                        dep_subs.prev_sub = link
                    link = cast("Link", dep.deps)
                    stack += 1
                    continue

            if not dirty and link and link.next_dep:
                link = link.next_dep
                continue

            if stack:
                sub = link.sub
                while stack:
                    stack -= 1
                    sub_subs = cast("Link", sub.subs)

                    if dirty:
                        if self.update_computed(cast("DependencyWithSubscriber", sub)):
                            if link := cast("Link", sub_subs.prev_sub):
                                sub_subs.prev_sub = None
                                self._shallow_propagate(sub_subs)
                                sub = link.sub
                            else:
                                sub = sub_subs.sub
                            continue
                    else:
                        sub.flags &= ~SubscriberFlags.PendingComputed

                    if link := cast("Link", sub_subs.prev_sub):
                        sub_subs.prev_sub = None
                        if link.next_dep:
                            link = link.next_dep
                            break  # Restart loop
                        sub = link.sub
                    else:
                        if link := cast("Link", sub_subs.next_dep):
                            break  # Restart loop
                        sub = sub_subs.sub

                    dirty = False

            return dirty

    def _shallow_propagate(self, link: Link) -> None:
        """Propagate PendingComputed status to Dirty for each subscriber in the chain.

        If the subscriber is also marked as an effect, it is added to
        self.queued_effects for later processing.

        Parameters
        ----------
        link : Link
            The head of the linked list to process.
        """
        while link:
            sub = link.sub
            sub_flags = sub.flags
            if (
                sub_flags & (SubscriberFlags.PendingComputed | SubscriberFlags.Dirty)
            ) == SubscriberFlags.PendingComputed:
                sub.flags = sub_flags | SubscriberFlags.Dirty | SubscriberFlags.Notified
                if (
                    sub_flags & (SubscriberFlags.Effect | SubscriberFlags.Notified)
                ) == SubscriberFlags.Effect:
                    if self.queued_effects_tail:
                        cast(
                            "Link",
                            self.queued_effects_tail.deps_tail,
                        ).next_dep = sub.deps
                    else:
                        self.queued_effects = sub
                    self.queued_effects_tail = sub
            link = cast("Link", link.next_sub)


def set_flags(sub: Subscriber, new_flags: int) -> typing.Literal[True]:
    sub.flags = cast("SubscriberFlags", new_flags)
    return True


def link_new_dep(
    dep: Dependency,
    sub: Subscriber,
    next_dep: Link | None,
    deps_tail: Link | None,
) -> Link:
    """Create and attach a new link between the given dependency and subscriber.

    If available, it reuses a link object from the link pool. The newly formed link
    is added to both the dependency's linked list and the subscriber's linked list.

    Parameters
    ----------
    dep : Dependency
        The dependency to link.
    sub : Subscriber
        The subscriber to be attached to this dependency.
    next_dep : Link or None
        The next link in the subscriber's chain.
    deps_tail : Link or None
        The current tail link in the subscriber's chain.

    Returns
    -------
    Link
        The newly created link object.
    """
    new_link = Link(
        dep=dep,
        sub=sub,
        next_dep=next_dep,
        prev_sub=None,
        next_sub=None,
    )

    if deps_tail is None:
        sub.deps = new_link
    else:
        deps_tail.next_dep = new_link

    if dep.subs is None:
        dep.subs = new_link
    else:
        old_tail = cast("Link", dep.subs_tail)
        new_link.prev_sub = old_tail
        old_tail.next_sub = new_link

    sub.deps_tail = new_link
    dep.subs_tail = new_link

    return new_link


def is_valid_link(check_link: Link, sub: Subscriber) -> bool:
    """Verify whether the given link is valid for the specified subscriber.

    It iterates through the subscriber's link list (from sub.deps to sub.deps_tail)
    to determine if the provided link object is part of that chain.

    Parameters
    ----------
    check_link : Link
        The link object to validate.
    sub : Subscriber
        The subscriber whose link list is being checked.

    Returns
    -------
    bool
        Whether the link is found in the subscriber's list.
    """
    deps_tail = sub.deps_tail
    if deps_tail is not None:
        link = sub.deps
        while link is not None:
            if link is check_link:
                return True
            if link is deps_tail:
                break
            link = link.next_dep
    return False


def clear_tracking(link: Link) -> None:
    """Clear dependency-subscription relationships starting at the given link.

    Detaches the link from both the dependency and subscriber, continuing to
    the next link in the chain. Links are returned to `link_pool` for reuse.

    Parameters
    ----------
    link : Link
        The head of a linked chain to be cleared.
    """
    while link:
        dep = link.dep
        next_dep = link.next_dep
        next_sub = link.next_sub
        prev_sub = link.prev_sub

        if next_sub:
            next_sub.prev_sub = prev_sub
        else:
            dep.subs_tail = prev_sub

        if prev_sub:
            prev_sub.next_sub = next_sub
        else:
            dep.subs = next_sub

        if dep.subs is None and hasattr(dep, "deps"):
            dep = cast("DependencyWithSubscriber", dep)
            dep_flags = dep.flags
            if not (dep_flags & SubscriberFlags.Dirty):
                dep.flags = dep_flags | SubscriberFlags.Dirty
            dep_deps = dep.deps
            if dep_deps:
                link = dep_deps
                cast("Link", dep.deps_tail).next_dep = next_dep
                dep.deps = None
                dep.deps_tail = None
                continue

        link = cast("Link", next_dep)
