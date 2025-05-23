package org.em.log.entity.common;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class DeviceIdentifier {

    @Column(nullable = false)
    private Long vehicleId;

    @Column(nullable = false)
    private Long mdn;
}
